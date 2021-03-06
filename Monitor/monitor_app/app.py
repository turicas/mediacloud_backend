#----------------------------------------------------------------------------#
# Imports.
#----------------------------------------------------------------------------#

import logging
from logging import Formatter, FileHandler
import json
import base64
import datetime
import re
import os

import pysolr
from flask import render_template, flash, request, redirect, url_for, Response
import pymongo
from bson import json_util
import bson
from pymongo.errors import ConnectionFailure
from jinja2 import Markup

from forms import *
import models
from appinit import app, db







#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#

# app = Flask(__name__)
# app.config.from_object('config')
# db = SQLAlchemy(app)

# Automatically tear down SQLAlchemy.
'''
@app.teardown_request
def shutdown_session(exception=None):
    db_session.remove()
'''

# Login required decorator.

#
# def login_required(test):
#     @wraps(test)
#     def wrap(*args, **kwargs):
#         if 'logged_in' in session:
#             return test(*args, **kwargs)
#         else:
#             flash('You need to login first.')
#             return redirect(url_for('login'))
#     return wrap

_paragraph_re = re.compile(r'(?:\r\n|\r|\n){2,}')


@app.template_filter('linebreaks')
def linebreaks(value):
    result = u'\n\n'.join(u'<p>%s</p>' % p.replace('\n', '<br>')
                          for p in _paragraph_re.split(value))
    return Markup(result)

#  Setup mongo connection
mongo_client = pymongo.MongoClient(app.config["MEDIACLOUD_DATABASE_HOST"])



@app.route('/dbstats')
def db_stats():
    """
    From GET take:  login, password : database credentials(optional, currently ignored)

    Return json with database stats,as returned by mongo (db.stats())
    """
    conf = models.Configuration.query.first()
    if not conf:
        return redirect(url_for('config'))
    host = conf.mongohost

    try:
        conn = pymongo.Connection(host=host, port=27017)
        db = conn.MCDB
        resp = db.command({'dbstats': 1})
        json_response = json.dumps({'data': resp}, default=json_util.default)
    except Exception, e:
        json_response = json.dumps({'error': repr(e)})
    finally:
        conn.disconnect()

    return Response(json_response, mimetype='application/json')
#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#


@app.route('/')
def home():
    conf = models.Configuration.query.first()
    if conf:
        data = {
            'host': conf.mongohost,
        }
    else:
        data = {}
    return render_template('pages/placeholder.home.html', data=data)


@app.route('/about')
def about():
    return render_template('pages/placeholder.about.html')

@app.route('/login')
def login():
    form = LoginForm(request.form)
    return render_template('forms/login.html', form = form)


@app.route('/register')
def register():
    form = RegisterForm(request.form)
    return render_template('forms/register.html', form = form)


@app.route('/forgot')
def forgot():
    form = ForgotForm(request.form)
    return render_template('forms/forgot.html', form = form)


@app.route('/config', methods=['GET', 'POST'])
def config():
    form = ConfigurationForm(request.form)
    if request.method == 'POST':
        c = models.Configuration(mongohost=form.dbhost.data, mongouser=form.dbuser.data, mongopasswd=form.dbpasswd.data, pyplnhost=form.pyplnhost.data,
                          pyplnuser=form.pyplnuser.data, pyplnpasswd=form.pyplnpasswd.data)
        db.session.add(c)
        db.session.commit()
        flash('Configuration saved')
        return redirect(url_for('home'))
    else:
        conf = models.Configuration.query.first()
        if conf:
            form.dbhost.data = conf.mongohost
            form.dbuser.data = conf.mongouser
            form.dbpasswd.data = conf.mongopasswd
            form.pyplnhost.data = conf.pyplnhost
            form.pyplnuser.data = conf.pyplnuser
            form.pyplnpasswd.data = conf.pyplnpasswd
    return render_template('forms/config.html', form=form)


@app.route('/feeds')
def feeds():
    nfeeds = mongo_client.MCDB.feeds.count()
    response = json.loads(fetch_docs('feeds'))

    if 'data' in response:
        feed_list = response['data']
    else:
        flash('Error searching for articles')
    try:
        keys = feed_list[0].keys()
    except KeyError:
        keys = ["No", "feeds", "in", "Database"]
    maintained_keys = set(['title', 'link', 'feed_link', 'language', 'published', 'last_visited'])


    return render_template('pages/feeds.html', nfeeds=nfeeds, keys=list(maintained_keys))


@app.route('/articles')
def articles():
    response = json.loads(fetch_docs('articles'))
    nart = mongo_client.MCDB.articles.count()
    q = request.args.get("query", "")

    maintained_keys = set(['title', 'summary', 'link', 'language', 'published'])
    # if response['data']:
    #     removed_fields = set(response['data'][0].keys()) - maintained_keys
    # else:
    #     removed_fields = set([])
    keys = []
    for feed in response['data']:
        keys += feed.keys()
    if not keys:
        keys = ["No", "Articles", "in", "Database"]
    return render_template('pages/articles.html', n_articles=nart, keys=list(maintained_keys), query=q)



def clean_articles(data):
    keys = []
    for feed in data:
        keys += feed.keys()
    maintained_keys = set(['title', 'summary', 'link', 'language', 'published'])
    removed_fields = set(keys) - maintained_keys
    article_list = []
    for article in data:
        for f in removed_fields:
            try:
                article.pop(f)
            except KeyError:
                pass
                #print f
        for f in maintained_keys:
            if f == 'language':
                article[f] = article[f]['name']
            if f == 'link':
                article[f] = r'<a href="{}">{}</a>'.format(article[f], article[f][:20]+'...')
                #print article[f]
            if f not in article:
                article[f] = 'NA'
        article_list.append(article)
        #print article_list
    if not article_list:
        flash('Error searching for articles')
    return article_list


def clean_feeds(data):
    """
    Clean JSON output to simplify table view
    """
    keys = []
    for feed in data:
        keys += feed.keys()

    maintained_keys = set(['title', 'link', 'language', 'published', 'last_visited', 'subtitle_detail'])
    removed_fields = set(keys) - maintained_keys
    feed_list = []
    for feed in data:
        for f in removed_fields:
            try:
                feed.pop(f)
            except KeyError:
                #print f
                pass
        for f in maintained_keys:
            if f not in feed:
                feed[f] = 'NA'
            if f == 'link':
                feed[f] = r'<a href="{}">{}</a>'.format(feed[f], feed[f][:20]+'...')
        try:
            if 'subtitle_detail' in feed:
                u = feed.get('base', feed['subtitle_detail'].get('base', 'NA'))
                feed['feed_link'] = r'<a href="{}">{}</a>'.format(u, u)
        except AttributeError:
            continue
        #print feed
        feed_list.append(feed)

    return feed_list


@app.route('/urls')
def urls():
    urls = json.loads(fetch_docs('urls'))
    try:
        keys = urls['data'][0].keys()
    except KeyError:
        keys = ["No", "URLs", "in", "Database"]
    return render_template('pages/urls.html', urls=urls, keys=keys)


@app.route("/feeds/json")
def json_feeds(start=0, stop=100):
    result = json.loads(fetch_docs('feeds', stop))
    return json.dumps({"aaData": clean_feeds(result['data'])})


@app.route("/articles/json")
@app.route("/articles/json/")
@app.route("/articles/json/<query>")
def json_articles(start=0, stop=100, query=""):
    if query:
        ids = [bson.ObjectId(d["_id"]) for d in json.loads(solr_query("mediacloud_articles", query).data)]
        result = json.loads(fetch_docs('articles', limit=10000, ids=ids))
        flash('Your query for {} matched articles.'.format(query))
    else:
        result = json.loads(fetch_docs('articles', limit=stop))
    articles = []
    for article in result['data']:
        article['published'] = datetime.date.fromtimestamp(article['published']['$date']/1000.).strftime("%b %d, %Y")
        article.pop('link_content')
        articles.append(article)

    return json.dumps({"aaData": clean_articles(articles)})

@app.route("/urls/json")
def json_urls(start=0, stop=100):
    return fetch_docs('urls', stop)


@app.route('/visualizations/timeline/')
def timeline():
    return render_template('pages/indextimeline.html')


@app.route('/visualizations/timeline/data.jsonp')
def json_timeline():
    Articles = json.loads(fetch_docs('articles'))['data']
    fixed_articles = []
    for art in Articles:
        art['published'] = datetime.date.fromtimestamp(art['published']['$date']/1000.).strftime("%Y,%m,%d")
        if 'summary_detail' not in art:
            art['summary_detail'] = {'value': ''}
        fixed_articles.append(art)

    dados = render_template('pages/timeline.json', busca='NAMD FGV', articles=fixed_articles)
    return Response(dados, mimetype='application/json')



@app.route("/query/<coll_name>", methods=['GET'])
def mongo_query(coll_name):
    """
    From GET take:  login, password : database credentials(optional, currently ignored)
         q -  mongo query as JSON dictionary
         sort - sort info (JSON dictionary)
         limit
         skip
         fields

    Return json with requested data or error
    """
    try:
        db = mongo_client.MCDB
        coll = db[coll_name]
        resp = {}
        query = json.loads(request.args.get('q', '{}'), object_hook=json_util.object_hook)
        limit = int(request.args.get('limit', 10))
        sort = request.args.get('sort', None)
        skip = int(request.args.get('skip', 0))
        if sort is not None:
            sort = json.loads(sort)
        cur = coll.find(query, skip=skip, limit=limit)
        cnt = cur.count()
        if sort is not None:
            cur = cur.sort(sort)
        resp = [a for a in cur]
        json_response = json.dumps({'data': fix_json_output(resp), 'meta': {'count': cnt}}, default=None)
    except Exception as e:
        app.logger.error(repr(e))
        # import traceback
        # traceback.print_stack()
        json_response = json.dumps({'error': repr(e)})
    resp = Response(json_response, mimetype='application/json',)
    return resp


@app.route("/solrquery/<index_name>/<query>", methods=["GET", "POST"])
def solr_query(index_name, query=""):
    """
    Perform a query in Solr server and return the documents stored in the index as JSON
    """
    try:
        assert index_name in ['mediacloud_articles', 'mediacloud_feeds']
    except AssertionError:
        flash('Wrong Index Name {}'.format(index_name))
        return redirect(url_for('home'))
    options = {
        'hl': 'true',
        'hl.fragsize': 10,
    }

    server = pysolr.Solr(os.path.join(app.config["SOLR_URL"], index_name))
    results = server.search(query, **options)
    return Response(json.dumps(results.docs), mimetype='application/json')

#-----------------------------#
# Utility functions
#-----------------------------#


def fix_json_output(json_obj):
    """
    Handle binary data in output json, because pymongo cannot encode them properly (generating UnicodeDecode exceptions)
    :param json_obj:
    """
    def _fix_json(d):
        if d in [None, [], {}]:  # if not d: breaks empty Binary
            return d
        data_type = type(d)
        if data_type == list:
            data = []
            for item in d:
                data.append(_fix_json(item))
            return data
        elif data_type == dict:
            data = {}
            for k in d:
                data[_fix_json(k)] = _fix_json(d[k])
            return data
        elif data_type == bson.Binary:
            ud = base64.encodestring(d)
            return {'$binary': ud, '$type': d.subtype }
        else:
            return d

    return _fix_json(json_obj)


def fetch_docs(colname, limit=100, ids=None):
    """
    Query MongoDB in the collection specified
    Return json with requested data or error.
    :param colname: Collection from which to fetch
    :param limit: maximum number of documents
    :param ids: list of ids to fetch.
    """
    try:
        db = mongo_client.MCDB
        coll = db[colname]
        resp = {}
        # query = json.loads(request.GET['q'], object_hook=json_util.object_hook)
        # limit = 10
        # sort = None
        # if 'limit' in request.GET:
        #     limit = int(request.GET['limit'])
        # skip = 0
        # if 'skip' in request.GET:
        #     skip = int(request.GET['skip'])
        # if 'sort' in request.GET:
        #     sort = json.loads(request.GET['sort'])
        if ids:
            cur = coll.find({"_id": {"$in": ids}}, sort=[("_id", pymongo.DESCENDING)], limit=limit)
        else:
            cur = coll.find({}, sort=[("_id", pymongo.DESCENDING)], limit=limit)
        cnt = cur.count()
        # if sort:
        #     cur = cur.sort(sort)
        resp = [a for a in cur]
        json_response = json.dumps({'data': fix_json_output(resp), 'meta': {'count': cnt}}, default=json_util.default)
    except ConnectionFailure:
        json_response = json.dumps({'error': "Can't connect to database on {}".format(app.config["MEDIACLOUD_DATABASE_HOST"])})
    except Exception, e:
        print e
        import traceback
        traceback.print_stack()
        json_response = json.dumps({'error': repr(e)})


    #resp = Response(json_response, mimetype='application/json' )
    #resp['Cache-Control'] = 'no-cache'
    return json_response


# Error handlers.

@app.errorhandler(500)
def internal_error(error):
    #db_session.rollback()
    return render_template('errors/500.html'), 500


@app.errorhandler(404)
def internal_error(error):
    return render_template('errors/404.html'), 404

if not app.debug:
    file_handler = FileHandler('error.log')
    file_handler.setFormatter(Formatter('%(asctime)s %(levelname)s: %(message)s '
    '[in %(pathname)s:%(lineno)d]'))
    app.logger.setLevel(logging.INFO)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.info('errors')

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

# Default port:
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

# Or specify port manually:
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
