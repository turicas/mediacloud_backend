#-*- coding:utf-8 -*-
u"""
Created on 04/02/14
by fccoelho
license: GPL V3 or Later

Script to index an entire mongo collection in batches into Solr
"""

import os
import sys
import zlib
import cPickle as CP
import time
import argparse
import pymongo
from solr_doc_manager import DocManager

sys.path.append('/'.join(os.getcwd().split("/")[:-1]))
from capture import settings


class Indexer(object):
    """
    Indexes a Mongodb Collection in batches to speed it up.
    """
    def __init__(self, url, core, collection):
        """
        """
        # self.solr = Solr(os.path.join(url, core))
        self.collection  = collection
        self.doc_manager = DocManager(os.path.join(url, core))

    def start(self, batchsize=100):
        """
        Starts the indexing
        """
        num_docs = self.collection.count()
        t0 = time.time()
        for i in range(0, num_docs, batchsize):
            cur = self.collection.find({}, skip=i, limit=batchsize, sort=[("_id", pymongo.DESCENDING)])
            try:
                docs = list(cur)
                self.doc_manager.bulk_upsert(docs)
                self.mark_as_indexed(docs, True)
            except Exception as e:
                self.mark_as_indexed(docs, False)
                print e
            print "indexed {} of {}".format(min(i+batchsize, num_docs), num_docs)
        print "Indexed {} documents per second.".format(num_docs/(time.time() - t0))

    def mark_as_indexed(self, docs, status):
        for doc in docs:
            self.collection.update({"_id": doc["_id"]}, {"$set": {"indexed": status}})

    def decompress(self, doc):
        """
        Decompresses and encodes HTML content
        """
        # Decompress the content of the article before sending to Solr
        doc["link_content"] = decompress_content(doc["link_content"]).encode('utf8')
        return doc


def decompress_content(compressed_html):
    """
    Decompress data compressed by `compress_content`
    :param compressed_html: compressed html document
    :return: original html
    """
    decompressed = zlib.decompress(compressed_html)
    orig_html = CP.loads(decompressed)
    return orig_html

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Push ARTICLE and FEED collections into SOLR for indexing')
    parser.add_argument('-b', '--batch_size', type=int, default=100, help='Batch size for each push to Solr')
    args = parser.parse_args()

    conn = pymongo.MongoClient(settings.MONGOHOST)
    article_indexer = Indexer(settings.SOLR_URL, "mediacloud_articles", conn.MCDB.articles)
    feed_indexer = Indexer(settings.SOLR_URL, "mediacloud_feeds", conn.MCDB.feeds)
    article_indexer.start(args.batch_size)
    feed_indexer.start(args.batch_size)



