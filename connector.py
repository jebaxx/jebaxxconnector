# -*- coding:utf-8 -*- 

import os
import flask
import json
import requests
import logging
import pickle
import StringIO
import re

import google.oauth2.credentials
import google_auth_oauthlib.flow
from google.appengine.api import app_identity
from google.appengine.api import taskqueue
import cloudstorage


CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES =["https://picasaweb.google.com/data/", 
	"https://www.googleapis.com/auth/userinfo.profile",
	"https://www.googleapis.com/auth/userinfo.email"]

app = flask.Flask(__name__)
app.secret_key = "*** SOME SECRET VALUE ***"

#@app.errorhandler(404)
#def error_handler(error):
#
#    msg = 'Error {code}\n'.format(code=error.code)
#    return msg, error.code

#-##############-###-############----###------------------------------------------
###
###	configページを表示
###-------------------------------------------------------------------------------
###
###	GET: 通常の表示
###	POST： フォーム内容によって処理内容をディスパッチする
###-------------------------------------------------------------------------------

@app.route('/config', methods=['GET','POST'])
def config():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())

    #-##############-###-############----###--------------------------
    #-POST内容（フォーム）により処理を振り分け（その１）

    if (flask.request.method == 'POST') and ('album_owners' in flask.request.form):

	#-##############-###-######---------
	#- owner_listフォームからのPOST
	#  押下されたボタンにより、Owner登録／アルバム再取得／Owner削除を行う

	logger.info("request: " + var_dump(flask.request.form))

	if (flask.request.form['action'] == u'新規登録') :
	    return flask.redirect('authorize')

	elif (flask.request.form['action'] == u'アルバム再取得') :
	    credentials = loadCredentials(flask.request.form['owner_id'])
	    owner_id = flask.request.form['owner_id']
	    getAlbums(owner_id, credentials)

	elif (flask.request.form['action'] == u'削除') :
	    owner_id = flask.request.form['owner_id']
	    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
	    fileName = bucketName + "/album_" + owner_id + ".pickle"
	    logger.info('** delete file : ' + fileName)
	    cloudstorage.delete(fileName)
	    fileName = bucketName + "/cred_" + owner_id + ".pickle"
	    cloudstorage.delete(fileName)

    #-##############-###-############----###--------------------------
    #- 表示データの読み込み（route_list）

    fileName = bucketName + "/sourcelist.json"
    fh = cloudstorage.open(fileName)
    route_list = json.loads(fh.read())
    fh.close()

    logger.info("route_list: " + var_dump(route_list))

    #-##############-###-############----###--------------------------
    #- 表示データの読み込み（owner_list）

    prefixFilter = bucketName + "/album_"
    files = cloudstorage.listbucket(prefixFilter)

    owner_list = {}

    for fileobj in files:
	logger.info('** file path = ' + fileobj.filename)
	matched = re.search("album_(.*)\.pickle$", fileobj.filename)
	owner_id = matched.group(1)

	fh = cloudstorage.open(fileobj.filename)
	encodedAlbums = fh.read()
	fh.close()

	owner_list[owner_id] = pickle.loads(encodedAlbums)

    logger.info("owner_list: " + var_dump(owner_list))

    #-##############-###-############----###--------------------------
    #-POST内容（フォーム）により処理を振り分け（その２）

    if (flask.request.method == 'POST') and ('route_edit' in flask.request.form):

	#-##############-###-######---------
	#- route_editフォームからのPOST
	#  登録ボタンが押されていたら、POSTされたFormデータ内容をroute_listに反映

    	logger.info("request: " + var_dump(flask.request.form))

	if (flask.request.form['action'] == u'登録') :


	    Line_id = flask.request.form['Line_id']

	    if (flask.request.form['owner_id'] == '-') :
		del route_list[Line_id]['owner_id']
		del route_list[Line_id]['album_id']
		del route_list[Line_id]['album_name']

	    else :
		route_list[Line_id]['owner_id'] = flask.request.form['owner_id']
		route_list[Line_id]['album_id'] = flask.request.form['album_id']
		route_list[Line_id]['album_name'] = owner_list[flask.request.form['owner_id']][flask.request.form['album_id']]
		route_list[Line_id]['name'] = flask.request.form['Line_name']

	    fileName = bucketName + "/sourcelist.json"
	    fh = cloudstorage.open(fileName, "w")
	    fh.write(json.dumps(route_list))
	    fh.close()

    i = 0
    for id in route_list.keys() :
	route_list[id]['label'] = 'lbl_' + str(i)
	i+=1

    if (flask.request.method == 'POST') and ('route_list' in flask.request.form):

	#-##############-###-######---------
	#- route_listフォームからのPOST
	#- route_infoデータを生成してroute_editフォーム(登録ルート編集)の初期値とする

    	logger.info("request: " + var_dump(flask.request.form))
	route_info = {}

	Line_id = flask.request.form['selected_route']
	selected_owner_id = route_list[Line_id].get('owner_id', '-')
	selected_album_id = route_list[Line_id].get('album_id', '-')

	route_info['Line_id']      = Line_id
	route_info['Line_name'] = route_list[Line_id]['name']
	route_info['owner_id'] = { '-': ('selected' if selected_owner_id == '-' else '') ,  }
	route_info['album_list']   = {}

	for owner_id in owner_list.keys():
	    route_info['owner_id'][owner_id] = 'selected' if owner_id == selected_owner_id else ''

	if (selected_owner_id != '-'):
	    for album_id, album_name in owner_list[selected_owner_id].iteritems():
		isSelected = 'selected' if album_id == selected_album_id else ''
		route_info['album_list'][album_id] = { 'name': album_name, 'selected': isSelected }

	logger.info("route_info : " +  var_dump(route_info))

	mode = {}
	mode['initial'] = 'disabled'
	mode['route_edit'] = ''
	return flask.render_template('connector_config.html', owner_list=owner_list, route_info=route_info, route_list=route_list, mode=mode);

    else:

	mode = {}
	mode['initial'] = ''
	mode['route_edit'] = 'disabled'
	return flask.render_template('connector_config.html', owner_list=owner_list, route_list=route_list, mode=mode)

###-------------------------------------------------------------------------------
###	Google アカウントの登録 
###-------------------------------------------------------------------------------

###----OAuth2認証----
###
@app.route('/authorize')
def authorize():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info('in authorize')

    try:
	flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)

	flow.redirect_uri = flask.url_for('oauth2callback', _external = True)
	authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true')
	logger.debug('get authorization url from flow : ' + authorization_url)

    except Exception:
	import traceback
	logger.error("Exception in authorize")
	logger.error(traceback.print_exc())
    
    flask.session['state'] = state

    return flask.redirect(authorization_url)

###----OAuth2認証コールバック----
###
@app.route('/oauth2callback')
def oauth2callback():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info('in oauth2callback.')

#    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    state = flask.session['state']

    try:
	flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)

	flow.redirect_uri = flask.url_for('oauth2callback', _external = True)
	authorization_response = flask.request.url
	logger.info('responce = ' + authorization_response)

	flow.fetch_token(authorization_response=authorization_response)
	credentials = flow.credentials
	logger.info('credentials acquired.')
	logger.info(var_dump(credentials))

	userId = get_userId(credentials)
	logger.info('userId: '+ userId + ' from credentials')
	saveCredentials(userId, credentials)

	albums = getAlbums(userId, credentials)

    except Exception:
	import traceback
	logger.error("Exception in authorization callback")
	logger.error(traceback.print_exc())

    return flask.redirect('config')

###----user profileを取得してUserIdを取り出す----
###
def get_userId(credentials):

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info('in get_userId.')

    url_profile = "https://www.googleapis.com/oauth2/v3/tokeninfo"
    params = ( ('id_token', credentials.id_token), )
    response = requests.get(url_profile, params = params)

    logger.info("acquired json file: " + response.text)

    profile = json.loads(response.text)
    mailaddr = profile['email']
    userId = mailaddr.split("@")[0].strip()

    return(userId)

###----credentialをcloudstorageに保存----
###
def saveCredentials(userId, credentials) :

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info('in saveCredentials.')

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    fileName = bucketName + '/cred_' + userId + '.pickle'
    logger.info('** file name = ' + fileName)

    fh = cloudstorage.open(fileName, 'w')
    fh.write(pickle.dumps(credentials))
    fh.close()


###----credentialをcloudstorageから取り出す----
###
def loadCredentials(userId):

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info('in loadCredenitals.')

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    fileName = bucketName + '/cred_' + userId + '.pickle'
    logger.info('** file name to be loaded is ' + fileName)

    try:
	fh = cloudstorage.open(fileName)
	credentials = pickle.loads(fh.read())
	fh.close()
    except cloudstorage.NotFoundError:
	import traceback
	logger.error("cannot load credentials file in storage")
	logger.error(traceback.print_exc())
	return

    if not credentials.valid:			# 期限切れの場合はrefresh要求を行う
	logger.info('credentials must be refresh.')
	import google.auth.transport.requests
	request = google.auth.transport.requests.Request()
	credentials.refresh(request)
	logger.info(var_dump(credentials))

	fh = cloudstorage.open(fileName, 'w')
	fh.write(pickle.dumps(credentials))
	fh.close()

    return (credentials)

###----credentialが持ち主であるphoto アルバム一覧を取得----
###
def getAlbums(userId, credentials):

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.debug("in getAlbum")

    url_albumList = "https://picasaweb.google.com/data/feed/api/user/" + userId
    params = ( ('access_token', credentials.token), )

    response = requests.get(url_albumList, params = params)

    import xml.etree.ElementTree
    root = xml.etree.ElementTree.fromstring(response.text.encode('utf-8'))
    nsmap = {'gphoto' : "http://schemas.google.com/photos/2007", 'Atom' : "http://www.w3.org/2005/Atom"}

    albums = {'-':'<default>'}
    for entry in root.findall(".//Atom:entry", nsmap):
    	albums[entry.find(".//gphoto:id", nsmap).text] = entry.find(".//Atom:title", nsmap).text

    encodedAlbums = pickle.dumps(albums)
    logger.info("album list : " + encodedAlbums);

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    fileName = bucketName + "/album_" + userId + ".pickle"
    logger.info('** file name = ' + fileName)

    fh = cloudstorage.open(fileName, 'w')
    fh.write(encodedAlbums)
    fh.close()

    return(albums)

###-------------------------------------------------------------------------------
###	写真登録タスクQueue
###-------------------------------------------------------------------------------

###----Queue handler----
###
###	タスクコール…>Album登録API実行（mp4に対応するための拡張バージョン：工事中）
###
@app.route('/enqueuePhoto', methods=['POST'])
def enqueuePhoto():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.debug("in EnqueuePhoto handler")

    logger.info(var_dump(flask.request.form))
    filename = flask.request.form['file']
    owner_id = flask.request.form['owner_id']
    album_id = flask.request.form['album_id']
    userId   = flask.request.form['Line_id']
    counter  = flask.request.form['counter']

    try:
	credentials = loadCredentials(owner_id)
    except Exception:
	import traceback
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())
#	pushMessage(userId, u"認証エラーで登録できない。もう一度設定し直してみて。")
	return("auth error"), _code

    if (album_id == '-'):
	requestUrl = 'https://picasaweb.google.com/data/feed/api/user/' + owner_id
    else:
	requestUrl = 'https://picasaweb.google.com/data/feed/api/user/' + owner_id + '/albumid/' + album_id

    logger.info("photo post endpoint = " + requestUrl)

    ### rulfetch config: set TIMEOUT = 120s
    ###
    from google.appengine.api import urlfetch
    urlfetch.set_default_fetch_deadline(600)
    ###

    xml_template = """<entry xmlns="http://www.w3.org/2005/Atom">
      <title>{0}</title>
      <category scheme="http://schemas.google.com/g/2005#kind"
        term="http://schemas.google.com/photos/2007#photo"/>
     </entry>"""

    try:
	_code = 500
	bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
	filepath = bucketName + '/photo_queue/' + filename
	fh = cloudstorage.open(filepath, mode='r')
	body, content_type = encode_multipart_related(
						xml_template.format(filename),
						fh.read(),
						'image/jpeg' if (re.search("\.(jpeg|jpg)", filename) != None) else 'video/mp4')
	fh.close()
	headers = { 'Content-Type': content_type }
	params = { 'access_token': credentials.token, 'uploadType': 'multipart' }
	response = requests.post(requestUrl, headers=headers, params=params, data=body)
	_code = response.status_code
	_req_h  = response.request.headers
	_req_b  = response.request.body[:400]
	logger.info("request headers : " + var_dump(_req_h))
	logger.info("request body : " + _req_b)

	if _code > 200 and _code < 299:
	    cloudstorage.delete(filepath)
	    logger.info("queued task coplete : " + str(_code))
	    return("OK"), _code
	else:
	    logger.warn("queued task error : " + str(_code))
#	    pushMessage(userId, u"うまく登録できない。")
	    return("enqueue error"), _code

    except Exception:
	import traceback
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())

    return("other error"), _code


###----create multipart request body----
###
###	Google photo Album に適合するマルチパートMIME request bodyの作成
###
from urllib3.filepost import encode_multipart_formdata, choose_boundary
from urllib3.fields   import RequestField

def encode_multipart_related(xml_metadata, content, content_type):

    rf1 = RequestField( name='placeholder', data=xml_metadata, headers={'Content-Type': 'application/atom+xml'} )
    rf2 = RequestField( name='placeholder2', data=content, headers={'Content-Type': content_type } )
    boundary = choose_boundary()

    body, _ = encode_multipart_formdata([rf1, rf2] , boundary)

    return body, 'multipart/related; boundary=%s' % boundary



###----Queue handler----
###
###	タスクコール…>Album登録API実行（jpegがうまくいったバージョン：一時退避）
###
@app.route('/enqueuePhoto0', methods=['POST'])
def enqueuePhoto0():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.debug("in EnqueuePhoto handler")

    logger.info(var_dump(flask.request.form))
    filename = flask.request.form['file']
    owner_id = flask.request.form['owner_id']
    album_id = flask.request.form['album_id']
    userId   = flask.request.form['Line_id']
    counter  = flask.request.form['counter']

    try:
	credentials = loadCredentials(owner_id)
    except Exception:
	import traceback
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())
#	pushMessage(userId, u"認証エラーで登録できない。もう一度設定し直してみて。")
	return("auth error"), _code

    if (album_id == '-'):
	requestUrl = 'https://picasaweb.google.com/data/feed/api/user/' + owner_id
    else:
	requestUrl = 'https://picasaweb.google.com/data/feed/api/user/' + owner_id + '/albumid/' + album_id

    logger.info("photo post endpoint = " + requestUrl)

    ### rulfetch config: set TIMEOUT = 60sec
    ###
    from google.appengine.api import urlfetch
    urlfetch.set_default_fetch_deadline(60.0)
    ###

	###
	###	THIS IS TEST!
	###

    xml_text = ""
    content  = "1234567890abcdefghijklmnopqrstuvwxyz"
    body, content_type = encode_multipart_related(xml_text, content, "image/jpeg")
    logger.info("body : " + body)
    logger.info("content_type : " + content_type)

	###
	###
	###

    try:
	_code = 500
	bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
	filepath = bucketName + '/photo_queue/' + filename
	headers = { 'Content-Type':'image/jpeg' if (re.search("\.(jpeg|jpg)", filename) != None) else 'video/mp4', 
		    'Content-Length':str(cloudstorage.stat(filepath).st_size), 
		    'Slug':filename }
	logger.info("headers : " + var_dump(headers))	####
	params = ( ('access_token', credentials.token), )
	fh = cloudstorage.open(filepath, mode='r')
	response = requests.post(requestUrl, headers=headers, params=params, data=fh.read())
	fh.close()
	_code = response.status_code
	if _code > 200 and _code < 299:
	    cloudstorage.delete(filepath)
	    logger.info("queued task coplete : " + str(_code))
	    return("OK"), _code
	else:
	    logger.warn("queued task error : " + str(_code))
#	    pushMessage(userId, u"うまく登録できない。")
	    return("enqueue error"), _code

    except Exception:
	import traceback
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())

    return("other error"), _code

###----Enqueue entry point----
###
###	サイト外からの登録要求受付⇒Queueへの登録
@app.route('/uploadRequestPoint', methods=['POST'])
def uploadRequestPoint():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.debug("in uploadRequestPoint")

    logger.info(var_dump(flask.request.form))
    Line_id = flask.request.form['source']
    filename = flask.request.form['filename']

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    routeFile = bucketName + "/sourcelist.json"
    fh = cloudstorage.open(routeFile)
    route_list = json.loads(fh.read())
    fh.close()

    params = {
	'file' : filename,
	'Line_id' : Line_id,
	'owner_id' : route_list[Line_id]['owner_id'],
	'album_id' : route_list[Line_id]['album_id'],
	'counter'  : flask.request.form['counter'] }

    try:
	task = taskqueue.add(url='/enqueuePhoto', params=params)
	logger.info("enqueued : name = " + task.name)

    except Exception:
	import traceback
	logger.error("Exception in uploadRequestPoint")
	logger.error(traceback.print_exc())

    return("OK")

###-------------------------------------------------------------------------------###

from pprint import pformat
import types

###############
## OBJ DUMP
##
def var_dump(obj):
    return pformat(dump(obj))

def dump(obj):
    '''return a printable representation of an object for debugging'''
    newobj = obj
    if isinstance(obj, list):
	# LIST
	newobj = []
	for item in obj:
	    newobj.append(dump(item))
    elif isinstance(obj, tuple):
	# TUPLE
	temp = []
	for item in obj:
	    temp.append(dump(item))
	newobj = tuple(temp)
    elif isinstance(obj, set):
	# SET
	temp = []
	for item in obj:
	    # DICTIONARY TO STRING
	    temp.append(str(dump(item)))
	newobj = set(temp)
    elif isinstance(obj, dict):
	# DICTIONARY
	newobj = {}
	for key, value in obj.items():
	    # DICTIONARY TO STRING
	    newobj[str(dump(key))] = dump(value)
    elif isinstance(obj, types.FunctionType):
	# FUNCTION
	newobj = repr(obj)
    elif '__dict__' in dir(obj):
	# NEW CLASS
	newobj = obj.__dict__.copy()
	if ' object at ' in str(obj) and not '__type__' in newobj:
	    newobj['__type__']=str(obj).replace(" object at ", " #").replace("__main__.", "")
	for attr in newobj:
	    newobj[attr]=dump(newobj[attr])
    return newobj
