#!/usr/bin/env python
"""
Fetches all urls in a google query for RSS feeds in Brasil
"""
__author__ = 'fccoelho'


import GoogleScraper
from urlparse import unquote
import pymongo
import logging
import settings
import argparse
import datetime
from pymongo.errors import DuplicateKeyError

##### Setup URL Collection ############
client = pymongo.MongoClient(settings.MONGOHOST, 27017)
MCDB = client.MCDB
URLS = MCDB.urls  # Collection of urls to extract feeds from
URLS.ensure_index('url', unique=True)
###########

def main(subject='', n=5):
    """
    Scrape google search up to the nth page and save the results to a MongoDB collection.
    :param n:
    """
    q = "{}+RSS+site:br".format(subject)
    for o in range(0, n*10, n):
        urls = GoogleScraper.scrape(q, number_pages=n, offset=o)
        for url in urls:
            # You can access all parts of the search results like that
            # url.scheme => URL scheme specifier (Ex: 'http')
            # url.netloc => Network location part (Ex: 'www.python.org')
            # url.path => URL scheme specifier (Ex: ''help/Python.html'')
            # url.params => Parameters for last path element
            # url.query => Query component
            #print url
            #print(unquote(url.geturl()))
            try:
                URLS.insert({'url': url, 'tags': [subject], 'fetched_on': datetime.datetime.now()})
            except DuplicateKeyError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Search for urls listing RSS feeds on with google')
    parser.add_argument('-s', '--subject', type=str, default='', help='subject of the FEEDS')
    args = parser.parse_args()
    main(args.subject)
