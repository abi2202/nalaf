from collections import OrderedDict
from itertools import chain
import json
import random
from nalaf.utils import MUT_CLASS_ID
import math
import re
from nalaf.utils.qmath import arithmetic_mean
from nalaf.utils.qmath import harmonic_mean
from nalaf import print_debug, print_verbose


class Dataset:
    """
    Class representing a group of documents.
    Instances of this class are the main object that gets passed around and modified by different modules.

    :type documents: dict
    """

    def __init__(self):
        self.documents = OrderedDict()
        """
        documents the dataset consists of, encoded as a dictionary
        where the key (string) is the id of the document, for example PubMed id
        and the value is an instance of Document
        """

    def __len__(self):
        """
        the length (size) of a dataset equals to the number of documents it has
        """
        return len(self.documents)

    def __iter__(self):
        """
        when iterating through the dataset iterate through each document
        """
        for doc_id, document in self.documents.items():
            yield document

    def __contains__(self, item):
        return item in self.documents

    def parts(self):
        """
        helper functions that iterates through all parts
        that is each part of each document in the dataset

        :rtype: collections.Iterable[Part]
        """
        for document in self:
            for part in document:
                yield part

    def annotations(self):
        """
        helper functions that iterates through all parts
        that is each part of each document in the dataset

        :rtype: collections.Iterable[Entity]
        """
        for part in self.parts():
            for annotation in part.annotations:
                yield annotation

    def predicted_annotations(self):
        """
        helper functions that iterates through all parts
        that is each part of each document in the dataset

        :rtype: collections.Iterable[Entity]
        """
        for part in self.parts():
            for annotation in part.predicted_annotations:
                yield annotation

    def relations(self):
        """
        helper function that iterates through all relations
        :rtype: collections.Iterable[Relation]
        """
        for part in self.parts():
            for rel in part.relations:
                yield rel

    def predicted_relations(self):
        """
        helper function that iterates through all predicted relations
        :rtype: collections.Iterable[Relation]
        """
        for part in self.parts():
            for relation in part.predicted_relations:
                yield relation

    def sentences(self):
        """
        helper functions that iterates through all sentences
        that is each sentence of each part of each document in the dataset

        :rtype: collections.Iterable[list[Token]]
        """
        for part in self.parts():
            for sentence in part.sentences:
                yield sentence

    def tokens(self):
        """
        helper functions that iterates through all tokens
        that is each token of each sentence of each part of each document in the dataset

        :rtype: collections.Iterable[Token]
        """
        for sentence in self.sentences():
            for token in sentence:
                yield token

    def edges(self):
        """
        helper function that iterations through all edges
        that is, each edge of each sentence of each part of each document in the dataset

        :rtype: collections.Iterable[Edge]
        """
        for part in self.parts():
            for edge in part.edges:
                yield edge

    def purge_false_relationships(self):
        """
        cleans false relationships by validating them
        :return:
        """
        for part in self.parts():
            part.relations[:] = [x for x in part.relations if x.validate_itself(part)]

    def partids_with_parts(self):
        """
        helper function that yields part id with part

        :rtype: collections.Iterable[(str, Part)]
        """
        for document in self:
            for part_id, part in document.key_value_parts():
                yield part_id, part

    def annotations_with_partids(self):
        """
        helper function that return annotation object with part id
        to be able to find out abstract or full document

        :rtype: collections.Iterable[(str, Entity)]
        """
        for part_id, part in self.partids_with_parts():
            for annotation in part.annotations:
                yield part_id, annotation

    def all_annotations_with_ids(self):
        """
        yields pubmedid, partid and ann through whole dataset

        :rtype: collections.Iterable[(str, str, Entity)]
        """
        for pubmedid, doc in self.documents.items():
            for partid, part in doc.key_value_parts():
                for ann in part.annotations:
                    yield pubmedid, partid, ann

    def all_annotations_with_ids_and_is_abstract(self):
        """
        yields pubmedid, partid, is_abstract and ann through whole dataset

        :rtype: collections.Iterable[(str, str, bool, Entity)]
        """
        for pubmedid, doc in self.documents.items():
            for partid, part in doc.key_value_parts():
                for ann in part.annotations:
                    yield pubmedid, partid, part.is_abstract, ann

    def label_edges(self):
        """
        label each edge with its target - whether it is indeed a relation or not
        """
        for edge in self.edges():
            if edge.is_relation():
                edge.target = 1
            else:
                edge.target = -1

    def form_predicted_annotations(self, class_id, aggregator_function=arithmetic_mean):
        """
        Populates part.predicted_annotations with a list of Annotation objects
        based on the values of the field predicted_label for each token.

        One annotation is the chunk of the text (e.g. mutation mention)
        whose tokens have labels that are continuously not 'O'
        For example:
        ... O O O A D I S A O O O ...
        ... ----- annotation ---- ...
        here the text representing the tokens 'A, D, I, S, A' will be one predicted annotation (mention).
        Assumes that the 'O' label means outside of mention.

        Requires predicted_label[0].value for each token to be set.
        """
        for part_id, part in self.partids_with_parts():
            for sentence in part.sentences:
                index = 0
                while index < len(sentence):
                    token = sentence[index]
                    confidence_values = []
                    if token.predicted_labels[0].value is not 'O':
                        start = token.start
                        confidence_values.append(token.predicted_labels[0].confidence)
                        while index + 1 < len(sentence) \
                                and sentence[index + 1].predicted_labels[0].value not in ('O', 'B', 'A'):
                            token = sentence[index + 1]
                            confidence_values.append(token.predicted_labels[0].confidence)
                            index += 1
                        end = token.start + len(token.word)
                        confidence = aggregator_function(confidence_values)
                        part.predicted_annotations.append(Entity(class_id, start, part.text[start:end], confidence))
                    index += 1

    def form_predicted_relations(self):
        """
        Populates part.predicted_relations with a list of Relation objects
        based on the values of the field target for each edge.

        Each Relation object denotes a relationship between two entities (usually)
        of different classes. Each relation is given by a relation type.

        Requires edge.target to be set for each edge.
        """
        for part in self.parts():
            for edge in part.edges:
                if edge.target == 1:
                    part.predicted_relations.append(Relation(edge.entity1.offset,
                                                        edge.entity2.offset,
                                                        edge.entity1.text,
                                                        edge.entity2.text,
                                                        edge.relation_type))

    def generate_top_stats_array(self, top_nr=10, is_alpha_only=False, class_id="e_2"):
        """
        An array for most occuring words.
        :param top_nr: how many top words are shown
        """
        # NOTE ambiguos words?

        raw_dict = {}

        for ann in self.annotations():
            for word in ann.text.split(" "):
                lc_word = word.lower()
                if lc_word.isalpha() and ann.class_id == class_id:
                    if lc_word not in raw_dict:
                        raw_dict[lc_word] = 1
                    else:
                        raw_dict[lc_word] += 1

        # sort by highest number
        sort_dict = OrderedDict(sorted(raw_dict.items(), key=lambda x: x[1], reverse=True ))
        print(json.dumps(sort_dict, indent=4))

    def clean_nl_definitions(self):
        """
        cleans all subclass = True to = False
        """
        for ann in self.annotations():
            ann.subclass = False

    def get_size_chars(self):
        """
        :return: total number of chars in this dataset
        """
        return sum(doc.get_size() for doc in self.documents.values())

    def __repr__(self):
        return "Dataset({0} documents and {1} annotations)".format(len(self.documents),
                                                                   sum(1 for _ in self.annotations()))

    def __str__(self):
        second_part = "\n".join(
            ["---DOCUMENT---\nDocument ID: '" + pmid + "'\n" + str(doc) for pmid, doc in self.documents.items()])
        return "----DATASET----\nNr of documents: " + str(len(self.documents)) + ', Nr of chars: ' + str(
            self.get_size_chars()) + '\n' + second_part

    def stats(self):
        """
        Calculates stats on the dataset. Like amount of nl mentions, ....
        """
        import re

        # main values
        nl_mentions = []  # array of nl mentions each of the the whole ann.text saved
        nl_nr = 0  # total nr of nl mentions
        nl_token_nr = 0  # total nr of nl tokens
        mentions_nr = 0  # total nr of all mentions (including st mentions)
        mentions_token_nr = 0  # total nr of all tokens of all mentions (inc st mentions)
        total_token_abstract = 0
        total_token_full = 0

        # abstract nr
        abstract_mentions_nr = 0
        abstract_token_nr = 0
        abstract_nl_mentions = []

        # full document nr
        full_document_mentions_nr = 0
        full_document_token_nr = 0
        full_nl_mentions = []

        # abstract and full document count
        abstract_doc_nr = 0
        full_doc_nr = 0

        # helper lists with unique pubmed ids that were already found
        abstract_unique_list = set([])
        full_unique_list = set([])

        # nl-docid set
        nl_doc_id_set = { 'empty' }

        # is abstract var
        is_abstract = True

        # precompile abstract match
        regex_abstract_id = re.compile(r'^s[12][shp]')

        for pubmedid, partid, is_abs, ann in self.all_annotations_with_ids_and_is_abstract():
            # abstract?
            if not is_abs:
                is_abstract = False
            else:
                if regex_abstract_id.match(partid) or partid == 'abstract':
                # NOTE added issue #80 for this
                    is_abstract = True
                else:
                    is_abstract = False


            if ann.class_id == MUT_CLASS_ID:
                # preprocessing
                token_nr = len(ann.text.split(" "))
                mentions_nr += 1
                mentions_token_nr += token_nr

                # TODO make parameterisable to just check for pure nl mentions
                if ann.subclass == 1 or ann.subclass == 2:
                    # total nr increase
                    nl_nr += 1
                    nl_token_nr += token_nr

                    # min doc attribute
                    if pubmedid not in nl_doc_id_set:
                        nl_doc_id_set.add(pubmedid)

                    # abstract nr of tokens increase
                    if is_abstract:
                        abstract_mentions_nr += 1
                        abstract_token_nr += token_nr
                        abstract_nl_mentions.append(ann.text)
                    else:
                        # full document nr of tokens increase
                        full_document_mentions_nr += 1
                        full_document_token_nr += token_nr
                        full_nl_mentions.append(ann.text)

                    # nl text mention add to []
                    nl_mentions.append(ann.text)

        # post-processing for abstract vs full document tokens
        for doc_id, doc in self.documents.items():
            for partid, part in doc.parts.items():
                if not part.is_abstract:
                    is_abs = False
                else:
                    is_abs = True
                    # if not regex_abstract_id.match(partid) and not 'abstract' in partid:
                    # # if regex_abstract_id.match(partid) or partid == 'abstract' or (len(partid) > 7 and partid[:8] == 'abstract'):
                    #     is_abs = False
                    # else:
                    #     is_abs = True

                if len(part.sentences) > 0:
                        tokens = sum(1 for sublist in part.sentences for _ in sublist)
                        # print(tokens, len(part.text.split(" ")))
                else:
                    tokens = False

                if not is_abs:
                    full_unique_list.add(doc_id)

                    if tokens:
                        total_token_full += tokens
                    else:
                        total_token_full += len(part.text.split(" "))
                else:
                    abstract_unique_list.add(doc_id)

                    if tokens:
                        total_token_abstract += tokens
                    else:
                        total_token_abstract += len(part.text.split(" "))

        abstract_unique_list = abstract_unique_list.difference(full_unique_list)
        abstract_doc_nr = len(abstract_unique_list)
        full_doc_nr = len(full_unique_list)

        report_dict = {
            'nl_mention_nr': nl_nr,
            'tot_mention_nr': mentions_nr,
            'nl_token_nr': nl_token_nr,
            'tot_token_nr': mentions_token_nr,
            'abstract_nl_mention_nr': abstract_mentions_nr,
            'abstract_nl_token_nr': abstract_token_nr,
            'abstract_tot_token_nr': total_token_abstract,
            'full_nl_mention_nr': full_document_mentions_nr,
            'full_nl_token_nr': full_document_token_nr,
            'full_tot_token_nr': total_token_full,
            'nl_mention_array': sorted(nl_mentions),
            'abstract_nr': abstract_doc_nr,
            'full_nr': full_doc_nr,
            'abstract_nl_mention_array': sorted(abstract_nl_mentions),
            'full_nl_mention_array': sorted(full_nl_mentions)
        }

        return report_dict

    def extend_dataset(self, other):
        """
        Does run on self and returns nothing. Extends the self-dataset with other-dataset.
        Each Document-ID that already exists in self-dataset gets skipped to add.
        :type other: nalaf.structures.data.Dataset
        """
        for key in other.documents:
            if key not in self.documents:
                self.documents[key] = other.documents[key]

    def prune(self):
        """
        deletes all the parts that contain no annotations at all
        """
        for doc_id, doc in self.documents.items():
            part_ids_to_del = []
            for part_id, part in doc.parts.items():
                if len(part.annotations) == 0:
                    part_ids_to_del.append(part_id)
            for part_id in part_ids_to_del:
                del doc.parts[part_id]

    def delete_subclass_annotations(self, subclass, predicted=True):
        """
        Method does delete all annotations that have subclass.
        Will not delete anything if not specified that particular subclass.
        :param subclass: annotation type to delete.
        :param no_predicted: if True it will only consider Part.annotations array and not Part.pred_annotations
        """
        if isinstance(subclass, int) or isinstance(subclass, str) or isinstance(subclass, bool):
            for part in self.parts():
                part.annotations = [ann for ann in part.annotations if ann.subclass != subclass]
                if predicted:
                    part.predicted_annotations = [ann for ann in part.predicted_annotations if ann.subclass != subclass]
        else:
            for subcl in subclass:
                for part in self.parts():
                    part.annotations = [ann for ann in part.annotations if ann.subclass != subcl]
                    if predicted:
                        part.predicted_annotations = [ann for ann in part.predicted_annotations if ann.subclass != subcl]

    def n_fold_split(self, n=5):
        """
        Returns N train, test random splits
        according to the standard N-fold cross validation scheme.

        :param n: number of folds
        :type n: int

        :return: a list of N train datasets and N test datasets
        :rtype: (list[nalaf.structures.data.Dataset], list[nalaf.structures.data.Dataset])
        """
        keys = list(sorted(self.documents.keys()))
        random.seed(2727)
        random.shuffle(keys)

        len_part = int(len(keys) / n)

        train = []
        test = []

        for fold in range(n):
            test_keys = keys[fold*len_part:fold*len_part+len_part]
            train_keys = [key for key in keys if key not in test_keys]

            test.append(Dataset())
            for key in test_keys:
                test[-1].documents[key] = self.documents[key]

            train.append(Dataset())
            for key in train_keys:
                train[-1].documents[key] = self.documents[key]
        return train, test

    def percentage_split(self, percentage=0.66):
        """
        Splits the dataset randomly into train and test dataset
        given the size of the train dataset in percentage.

        :param percentage: the size of the train dataset between 0.0 and 1.0
        :type percentage: float

        :return train dataset, test dataset
        :rtype: (nalaf.structures.data.Dataset, nalaf.structures.data.Dataset)
        """
        keys = list(sorted(self.documents.keys()))
        # 2727 is an arbitrary number when Alex was drunk one day, and it's just to have reliable order in data folds randomization
        random.seed(2727)
        random.shuffle(keys)

        len_train = int(len(keys) * percentage)
        train_keys = keys[:len_train]
        test_keys = keys[len_train:]

        train = Dataset()
        test = Dataset()

        for key in test_keys:
            test.documents[key] = self.documents[key]
        for key in train_keys:
            train.documents[key] = self.documents[key]

        return train, test


class Document:
    """
    Class representing a single document, for example an article from PubMed.

    :type parts: dict
    """

    def __init__(self):
        self.parts = OrderedDict()
        """
        parts the document consists of, encoded as a dictionary
        where the key (string) is the id of the part
        and the value is an instance of Part
        """

    def __eq__(self, other):
        return self.get_size() == other.get_size()

    def __lt__(self, other):
        return self.get_size() - other.get_size() < 0

    def __iter__(self):
        """
        when iterating through the document iterate through each part
        """
        for part_id, part in self.parts.items():
            yield part

    def __repr__(self):
        if self.get_text() == self.get_body():
            return 'Document(Size: {}, Text: "{}", Annotations: "{}")'.format(len(self.parts), self.get_text(),
                                                                                 self.get_unique_mentions())
        else:
            return 'Document(Size: {}, Title: "{}", Text: "{}", Annotations: "{}")'.format(len(self.parts),
                                                                                               self.get_title(),
                                                                       self.get_text(), self.get_unique_mentions())

    def __str__(self):
        partslist = ['--PART--\nPart ID: "' + partid + '"\n' + str(part) + "\n" for partid, part in self.parts.items()]
        second_part = "\n".join(partslist)
        return 'Size: ' + str(self.get_size()) + ", Title: " + self.get_title() + '\n' + second_part

    def key_value_parts(self):
        """yields iterator for partids"""
        for part_id, part in self.parts.items():
            yield part_id, part

    def get_unique_mentions(self):
        """:return: set of all mentions (standard + natural language)"""
        mentions = []
        for part in self:
            for ann in part.annotations:
                mentions.append(ann.text)

        return set(mentions)

    def unique_relations(self, rel_type, predicted=False):
        """
        :param predicted: iterate through predicted relations or true relations
        :type predicted: bool
        :return: set of all relations (ignoring the text offset and
        considering only the relation text)
        """
        relations = []
        for part in self:
            if predicted:
                relation_list = part.predicted_relations
            else:
                relation_list = part.relations
            for rel in relation_list:
                entity1, relation_type, entity2 = rel.get_relation_without_offset()
                if entity1 < entity2:
                    relation_string = entity1+' '+relation_type+' '+entity2
                else:
                    relation_string = entity2+' '+relation_type+' '+entity1
                if relation_string not in relations and relation_type == rel_type:
                    relations.append(relation_string)
        return set(relations)

    def relations(self):
        """  helper function for providing an iterator of relations on document level """
        for part in self.parts.values():
            for rel in part.relations:
                yield rel

    def purge_false_relationships(self):
        """
        purging false relationships (that do not return true if validating themselves)
        :return:
        """
        for part in self.parts:
            part.relations[:] = [x for x in part.relations if x.validate_itself(part)]

    def get_size(self):
        """returns nr of chars including spaces between parts"""
        return sum(len(x.text) + 1 for x in self.parts.values()) - 1

    def get_title(self):
        """:returns title of document as str"""
        if len(self.parts.keys()) == 0:
            return ""
        else:
            return list(self.parts.values())[0].text

    def get_text(self):
        """
        Gives the whole text concatenated with spaces in between.
        :return: string
        """
        text = ""

        _length = self.get_size()

        for i, p in enumerate(self.parts.values()):
            if _length - 1 == i:
                text += p.text
                break
            text += "{0} ".format(p.text)
        return text.strip()

    def get_body(self):
        """
        :return: Text without title. No '\n' and spaces between parts.
        """
        text = ""
        size = len(self.parts)
        for i, (_, part) in enumerate(self.parts.items()):
            if i > 0:
                if i < size - 1:
                    text += part.text.strip() + " "
                else:
                    text += part.text.strip()
        return text

    def overlaps_with_mention2(self, start, end):
        """
        Checks for overlap with given 2 nrs that represent start and end position of any corresponding string.
        :param start: index of first char (offset of first char in whole document)
        :param end: index of last char (offset of last char in whole document)
        """
        print_verbose('Searching for overlap with a mention.')
        Entity.equality_operator = 'exact_or_overlapping'
        query_ann = Entity(class_id='', offset=start, text=(end - start + 1) * 'X')
        print_debug(query_ann)
        offset = 0
        for part in self.parts.values():
            print_debug('Query: Offset =', offset, 'start char =', query_ann.offset, 'start char + len(ann.text) =',
                        query_ann.offset + len(query_ann.text), 'params(start, end) =',
                        "({0}, {1})".format(start, end))
            for ann in part.annotations:
                offset_corrected_ann = Entity(class_id='', offset=ann.offset + offset, text=ann.text)
                if offset_corrected_ann == query_ann:
                    print_verbose('Found annotation:', ann)
                    return True
                else:
                    print_debug(
                        "Current(offset: {0}, offset+len(text): {1}, text: {2})".format(offset_corrected_ann.offset,
                                                                                        offset_corrected_ann.offset + len(
                                                                                            offset_corrected_ann.text),
                                                                                        offset_corrected_ann.text))
            offset += len(part.text)
        return False

    def overlaps_with_mention(self, *span, annotated=True):
        """
        Checks for overlap at position charpos with another mention.
        """
        offset = 0

        if len(span) == 2:
            start, end = span
        else:
            start, end = span[0]
        # todo check again with *span and unpacking

        print_debug("===TEXT===\n{0}\n".format(self.get_text()))

        for pid, part in self.parts.items():
            print_debug("Part {0}: {1}".format(pid, part))
            if annotated:
                annotations = part.annotations
            else:
                annotations = part.predicted_annotations
            for ann in annotations:
                print_debug(ann)
                print_debug("TEXT:".ljust(10) + part.text)
                print_debug("QUERY:".ljust(10) + "o" * (start - offset) + "X" * (end - start + 1) + "o" * (
                    len(part.text) - end + offset - 1))
                print_debug("CURRENT:".ljust(10) + ann.text.rjust(ann.offset + len(ann.text), 'o') + 'o' * (
                        len(part.text) - ann.offset + len(ann.text) - 2))
                if start < ann.offset + offset + len(ann.text) and ann.offset + offset <= end:
                    print_verbose('=====\nFOUND\n=====')
                    print_verbose("TEXT:".ljust(10) + part.text)
                    print_verbose("QUERY:".ljust(10) + "o" * (start - offset) + "X" * (end - start + 1) + "o" * (
                        len(part.text) - end + offset - 1))
                    print_verbose("FOUND:".ljust(10) + ann.text.rjust(ann.offset + len(ann.text), 'o') + 'o' * (
                        ann.offset + len(ann.text) - 1))
                    return True
            offset += len(part.text) + 1
        print_verbose('=========\nNOT FOUND\n=========')
        print_verbose(
            "QUERY:".ljust(10) + "o" * start + "X" * (end - start + 1) + "o" * (offset - end - 2))
        print_verbose("TEXT:".ljust(10) + self.get_text())
        print_debug()
        return False


class Part:
    """
    Represent chunks of text grouped in the document that for some reason belong together.
    Each part hold a reference to the annotations for that chunk of text.

    :type text: str
    :type sentences: list[list[Token]]
    :type annotations: list[Entity]
    :type predicted_annotations: list[Entity]
    :type is_abstract: bool
    """

    def __init__(self, text, is_abstract=True):
        self.text = text
        """the original raw text that the part is consisted of"""
        self.sentences = [[]]
        """
        a list sentences where each sentence is a list of tokens
        derived from text by calling Splitter and Tokenizer
        """
        self.annotations = []
        """the annotations of the chunk of text as populated by a call to Annotator"""
        self.predicted_annotations = []
        """
        a list of predicted annotations as populated by a call to form_predicted_annotations()
        this represent the prediction on a mention label rather then on a token level
        """
        self.relations = []
        """
        a list of relations that represent a connection between 2 annotations e.g. mutation mention and protein,
        where the mutation occurs inside
        """
        self.predicted_relations = []
        """a list of predicted relations as populated by a call to form_predicted_relations()"""
        self.edges = []
        """a list of possible relations between any two entities in the part"""
        self.is_abstract = is_abstract
        """whether the part is the abstract of the paper"""
        self.sentence_parse_trees = []
        """the parse trees for each sentence stored as a string"""
        self.tokens = []

    def get_sentence_string_array(self):
        """ :returns an array of string in which each index contains one sentence in type string with spaces between tokens """
        return_array = []
        for sentence_array in self.sentences:
            new_sentence = ""
            for token in sentence_array:
                if isinstance(token, Token):
                    new_sentence += token.word + " "
                else:
                    return self.sentences
            return_array.append(new_sentence.rstrip())  # to delete last space
        return return_array

    def get_sentence_index_for_annotation(self, annotation):
        start = annotation.offset
        end = annotation.offset + len(annotation.text)
        for index, sentence in enumerate(self.sentences):
            for token in sentence:
                if start <= token.start <= end:
                    return index

    def get_entities_in_sentence(self, sentence_id, entity_classId):
        """
        get entities of a particular type in a particular sentence

        :param sentence_id: sentence number in the part
        :type sentence_id: int
        :param entity_classId: the classId of the entity
        :type entity_classId: str
        """
        sentence = self.sentences[sentence_id]
        start = sentence[0].start
        end = sentence[-1].end
        entities = []
        for annotation in self.annotations:
            if start <= annotation.offset < end and annotation.class_id == entity_classId:
                entities.append(annotation)
        return entities

    def percolate_tokens_to_entities(self, annotated=True):
        """
        if entity start and token start, and entity end and token end match,
        store tokens directly.
        if entity start and token start or entity end and token end don't match
        store the nearest entity having index just before for the start of the
        entity and just after for the end of the entity
        """
        for entity in chain(self.annotations, self.predicted_annotations):
            entity.tokens = []
            entity_end = entity.offset + len(entity.text)
            for token in self.tokens:
                if entity.offset <= token.start < entity_end or \
                    token.start <= entity.offset < token.end:
                    entity.tokens.append(token)

    # TODO move to edge features
    def calculate_token_scores(self):
        """
        calculate score for each entity based on a simple heuristic of which
        token is closest to the root based on the dependency tree.
        """
        not_tokens = []
        important_dependencies = ['det', 'amod', 'appos', 'npadvmod', 'compound',
                'dep', 'with', 'nsubjpass', 'nsubj', 'neg', 'prep', 'num', 'punct']
        for sentence in self.sentences:
            for token in sentence:
                if token.word not in not_tokens:
                    token.features['score'] = 1
                if token.features['dependency_from'][0].word not in not_tokens:
                    token.features['dependency_from'][0].features['score'] = 1

            done = False
            counter = 0

            while(not done):
                done = True
                for token in sentence:
                    dep_from = token.features['dependency_from'][0]
                    dep_to = token
                    dep_type = token.features['dependency_from'][1]

                    if dep_type in important_dependencies:
                        if dep_from.features['score'] <= dep_to.features['score']:
                            dep_from.features['score'] = dep_to.features['score'] + 1
                            done = True
                counter += 1
                if counter > 20:
                    break

    def set_head_tokens(self):
        """
        set head token for each entity based on the scores for each token
        """
        for token in self.tokens:
            if token.features['score'] is None:
                token.features['score'] = 1

        for entity in chain(self.annotations, self.predicted_annotations):
            if len(entity.tokens) == 1:
                entity.head_token = entity.tokens[0]
            else:
                entity.head_token = max(entity.tokens, key=lambda token: token.features['score'])

    def __iter__(self):
        """
        when iterating through the part iterate through each sentence
        """
        return iter(self.sentences)

    def __repr__(self):
        return "Part(is abstract = {abs}, len(sentences) = {sl}, ' \
        'len(anns) = {al}, len(pred anns) = {pl}, ' \
        'len(rels) = {rl}, len(pred rels) = {prl}, ' \
        'text = \"{self.text}\")".format(
            self=self, sl=len(self.sentences),
            al=len(self.annotations), pl=len(self.predicted_annotations),
            rl=len(self.relations), prl=len(self.predicted_relations),
            abs=self.is_abstract)

    def __str__(self):
        annotations_string = "\n".join([str(x) for x in self.annotations])
        pred_annotations_string = "\n".join([str(x) for x in self.predicted_annotations])
        relations_string = "\n".join([str(x) for x in self.relations])
        pred_relations_string = "\n".join([str(x) for x in self.predicted_relations])
        if not annotations_string:
            annotations_string = "[]"
        if not pred_annotations_string:
            pred_annotations_string = "[]"
        if not relations_string:
            relations_string = "[]"
        if not pred_relations_string:
            pred_relations_string = "[]"
        return 'Is Abstract: {abstract}\n-Text-\n"{text}"\n-Annotations-\n{annotations}\n' \
               '-Predicted annotations-\n{pred_annotations}\n' \
               '-Relations-\n{relations}\n' \
               '-Predicted relations-{pred_relations}'.format(
                        text=self.text, annotations=annotations_string,
                        pred_annotations=pred_annotations_string, relations=relations_string,
                        pred_relations=pred_relations_string, abstract=self.is_abstract)

    def get_size(self):
        """ just returns number of chars that this part contains """
        # OPTIONAL might be updated in order to represent annotations and such as well
        return len(self.text)


class Edge:
    """
    Represent an edge - a possible relation between two named entities.

    :type entity1: nalaf.structures.data.Entity
    :type entity2: nalaf.structures.data.Entity
    :type relation_type: str
    :type sentence: list[nalaf.structures.data.Token]
    :type sentence_id: int
    :type part: nalaf.structures.data.Part
    :type features: dict
    """

    def __init__(self, entity1, entity2, relation_type, sentence, sentence_id, part):
        self.entity1 = entity1
        """The first entity in the edge"""
        self.entity2 = entity2
        """The second entity in the edge"""
        self.relation_type = relation_type
        """The type of relationship between the two entities"""
        self.sentence = sentence
        """The sentence which contains the edge"""
        # TODO Design decision, whether to retain sentence or retain part and sentence id
        # Part and Sentence ID might make sense for double sentence relationships
        self.sentence_id = sentence_id
        """The index of the sentence mentioned in sentence"""
        self.part = part
        """The part in which the sentence is contained"""
        self.features = {}
        """
        a dictionary of features for the edge
        each feature is represented as a key value pair:
        """
        self.target = None
        """class of the edge - True or False or any other float value"""

    def is_relation(self):
        """
        check if the edge is present in part.relations.
        :rtype: bool
        """
        relation_1 = Relation(self.entity1.offset, self.entity2.offset, self.entity1.text, self.entity2.text, self.relation_type)
        relation_2 = Relation(self.entity2.offset, self.entity1.offset, self.entity2.text, self.entity1.text, self.relation_type)
        for relation in self.part.relations:
            if relation_1 == relation:
                return True
            if relation_2 == relation:
                return True
        return False

    def __repr__(self):
        """
        print calls to the class Token will print out the string contents of the word
        """
        return 'Edge between "{0}" and "{1}" of the type "{2}".'.format(self.entity1.text, self.entity2.text, self.relation_type)


class Token:
    """
    Represent a token - the smallest unit on which we perform operations.
    Usually one token represent one word from the document.

    :type word: str
    :type original_labels: list[Label]
    :type predicted_labels: list[Label]
    :type features: FeatureDictionary
    """

    def __init__(self, word, start):
        self.word = word
        """string value of the token, usually a single word"""
        self.start = start
        """start offset of the token in the original text"""
        self.end = self.start + len(self.word)
        """end offset of the token in the original text"""
        self.original_labels = None
        """the original labels for the token as assigned by some implementation of Labeler"""
        self.predicted_labels = None
        """the predicted labels for the token as assigned by some learning algorightm"""
        self.features = FeatureDictionary()
        """
        a dictionary of features for the token
        each feature is represented as a key value pair:
        * [string], [string] pair denotes the feature "[string]=[string]"
        * [string], [float] pair denotes the feature "[string]:[float] where the [float] is a weight"
        """

    def is_entity_part(self, part):
        """
        check if the token is part of an entity
        :return bool:
        """
        for entity in part.annotations:
            if self.start <= entity.offset < self.end:
                return True
        return False

    def get_entity(self, part):
        """
        if the token is part of an entity, return the entity else return None
        :param part: an object of type Part in which to search for the entity.
        :type part: nalaf.structures.data.Part
        :return nalaf.structures.data.Entity or None
        """
        for entity in part.annotations:
            if self.start <= entity.offset < self.end:
                # entity.offset <= self.start < entity.offset + len(entity.text):
                return entity
        return None

    # TODO review this method
    def masked_text(self, part):
        """
        if token is part of an entity, return the entity class id, otherwise
        return the token word itself.
        :param part: an object of type Part in which to search for the entity.
        :type part: nalaf.structures.data.Part
        :return str
        """
        for entity in part.annotations:
            if self.start <= entity.offset < self.end: # or \
                # entity.offset <= self.start < entity.offset + len(entity.text):
                return entity.class_id
        return self.word

    def __repr__(self):
        """
        print calls to the class Token will print out the string contents of the word
        """
        return self.word

    def __eq__(self, other):
        """
        consider two tokens equal if and only if their token words and start
        offsets coincide.
        :type other: nalaf.structures.data.Token
        :return bool:
        """
        if hasattr(other, 'word') and hasattr(other, 'start'):
            if self.word == other.word and self.start == other.start:
                return True
            else:
                return False
        else:
            return False

    def __ne__(self, other):
        """
        :type other: nalaf.structures.data.Token
        :return bool:
        """
        return not self.__eq__(other)


class FeatureDictionary(dict):
    """
    Extension of the built in dictionary with the added constraint that
    keys (feature names) cannot be updated.

    If the key (feature name) doesn't end with "[number]" appends "[0]" to it.
    This is used to identify the position in the window for the feature.

    Raises an exception when we try to add a key that exists already.
    """

    def __setitem__(self, key, value):
        if key in self:
            raise KeyError('feature name "{}" already exists'.format(key))
        else:
            if not re.search('\[-?[0-9]+\]$', key):
                key += '[0]'
            dict.__setitem__(self, key, value)


class Entity:
    """
    Represent a single annotation, that is denotes a span of text which represents some entity.

    :type class_id: str
    :type offset: int
    :type text: str
    :type subclass: int
    :type confidence: float
    :type normalisation_dict: dict
    :type normalized_text: str
    :type tokens: list[nalaf.structures.data.Token]
    :type head_token: nalaf.structures.data.Token
    """
    def __init__(self, class_id, offset, text, confidence=1):
        self.class_id = class_id
        """the id of the class or entity that is annotated"""
        self.offset = offset
        """the offset marking the beginning of the annotation in regards to the Part this annotation is attached to."""
        self.text = text
        """the text span of the annotation"""
        self.subclass = False
        """
        int flag used to further subdivide classes based on some criteria
        for example for mutations (MUT_CLASS_ID): 0=standard, 1=natural language, 2=semi standard
        """
        self.confidence = confidence
        """aggregated mention level confidence from the confidence of the tokens based on some aggregation function"""
        self.normalisation_dict = {}
        """ID in some normalization database of the normalized text for the annotation if normalization was performed"""
        self.normalized_text = ''
        """the normalized text for the annotation if normalization was performed"""
        self.tokens = []
        """the tokens in each entity"""
        self.head_token = None
        """the head token for the entity"""

    equality_operator = 'exact'
    """
    determines when we consider two annotations to be equal
    can be "exact" or "overlapping" or "exact_or_overlapping"
    """

    def __repr__(self):
        norm_string = ''
        if self.normalisation_dict:
            norm_string = ', Normalisation Dict: {0}, Normalised text: "{1}"'.format(self.normalisation_dict, self.normalized_text)
        return 'Entity(ClassID: "{self.class_id}", Offset: {self.offset}, ' \
               'Text: "{self.text}", SubClass: {self.subclass}, ' \
               'Confidence: {self.confidence}{norm})'.format(self=self, norm=norm_string)

    def __eq__(self, other):
        # consider them a match only if class_id matches
        # TODO implement test case for edge cases in overlap and exact
        if self.class_id == other.class_id:
            exact = self.offset == other.offset and self.text == other.text
            overlap = self.offset < (other.offset + len(other.text)) and (self.offset + len(self.text)) > other.offset

            if self.equality_operator == 'exact':
                return exact
            elif self.equality_operator == 'overlapping':
                # overlapping means only the case where we have an actual overlap and not exact match
                return not exact and overlap
            elif self.equality_operator == 'exact_or_overlapping':
                # overlap includes the exact case so just return that
                return overlap
            else:
                raise ValueError('other must be "exact" or "overlapping" or "exact_or_overlapping"')
        else:
            return False


class Label:
    """
    Represents the label associated with each Token.

    :type value: str
    :type confidence: float
    """

    def __init__(self, value, confidence=None):
        self.value = value
        """string value of the label"""
        self.confidence = confidence
        """probability of being correct if the label is predicted"""

    def __repr__(self):
        return self.value


class Relation:
    """
    Represents a relationship between 2 annotations.
    :type start1: int
    :type start2: int
    :type text1: str
    :type text2: str
    :type class_id: str
    """

    def __init__(self, start1, start2, text1, text2, type_of_relation):
        self.start1 = start1
        self.start2 = start2
        self.text1 = text1
        self.text2 = text2
        self.class_id = type_of_relation

    def __repr__(self):
        return 'Relation(Class ID:"{self.class_id}", Start1:{self.start1}, Text1:"{self.text1}", ' \
               'Start2:{self.start2}, Text2:"{self.text2}")'.format(self=self)

    def get_relation_without_offset(self):
        """:return string with entity1 and entity2 separated by relation type"""
        return (self.text1, self.class_id, self.text2)

    def validate_itself(self, part):
        """
        validation of itself with annotations and the text
        :param part: the part where this relation is saved inside
        :type part: nalaf.structures.data.Part
        :return: bool
        """
        first = False
        second = False
        for ann in chain(part.annotations, part.predicted_annotations):
            if ann.offset == self.start1 and ann.text == self.text1:
                first = True
            if ann.offset == self.start2 and ann.text == self.text2:
                second = True
            if first and second:
                return True
        return False

    def __eq__(self, other):
        """
        consider two relations equal if and only if all their parameters match
        :type other: nalaf.structures.data.Relation
        :return bool:
        """
        if other is not None:
            return self.__dict__ == other.__dict__
        else:
            return False

    def __ne__(self, other):
        """
        :type other: nalaf.structures.data.Relation
        :return bool:
        """
        if other is not None:
            return not self.__dict__ == other.__dict__
        else:
            return False