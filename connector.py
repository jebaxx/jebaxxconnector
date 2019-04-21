# -*- coding:utf-8 -*- 

import os
import flask
import json
import requests
import logging
import pickle
import StringIO
import re
import traceback

import google.oauth2.credentials
import google_auth_oauthlib.flow
from google.appengine.api import app_identity
from google.appengine.api import taskqueue
import cloudstorage


CLIENT_SECRETS_FILE = "client_secret.json"
#SCOPES =["https://picasaweb.google.com/data/", 
SCOPES =["https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
	"https://www.googleapis.com/auth/photoslibrary.appendonly",
	"https://www.googleapis.com/auth/userinfo.profile",
	"https://www.googleapis.com/auth/userinfo.email"]

app = flask.Flask(__name__)
app.secret_key = "*** SOME SECRET VALUE ***"

loggingLevel = logging.INFO

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
    logger.setLevel(loggingLevel)
    
    logger.info("config method = " + flask.request.method)

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())

    #-##############-###-############----###--------------------------
    #-POST内容（フォーム）により処理を振り分け（その１）

    if (flask.request.method == 'POST') and ('album_owners' in flask.request.form):

	logger.info("Edit google account list")

	#-##############-###-######---------
	#- owner_listフォームからのPOST
	#  押下されたボタンにより、Owner登録／アルバム再取得／Owner削除を行う

	logger.debug("request: " + var_dump(flask.request.form))

	if (flask.request.form['action'] == u'新規登録') :
	    return flask.redirect('authorize')

	elif (flask.request.form['action'] == u'アルバム再取得') :
	    credentials = loadCredentials(flask.request.form['owner_id'])
	    owner_id = flask.request.form['owner_id']
	    logger.info("Get album list of " + owner_id)
	    getAlbums(owner_id, credentials)

	elif (flask.request.form['action'] == u'削除') :
	    owner_id = flask.request.form['owner_id']
	    logger.info("Delete google account :" + owner_id)
	    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
	    fileName = bucketName + "/album_" + owner_id + ".pickle"
	    logger.debug('** delete file : ' + fileName)
	    cloudstorage.delete(fileName)
	    fileName = bucketName + "/cred_" + owner_id + ".pickle"
	    cloudstorage.delete(fileName)

    #-##############-###-############----###--------------------------
    #- 表示データの読み込み（route_list）

    fileName = bucketName + "/sourcelist.json"
    fh = cloudstorage.open(fileName)
    route_list = json.loads(fh.read())
    fh.close()

    logger.debug("route_list: " + var_dump(route_list))

    #-##############-###-############----###--------------------------
    #- 表示データの読み込み（owner_list）

    prefixFilter = bucketName + "/album_"
    files = cloudstorage.listbucket(prefixFilter)

    owner_list = {}

    for fileobj in files:
	logger.debug('** file path = ' + fileobj.filename)
	matched = re.search("album_(.*)\.pickle$", fileobj.filename)
	owner_id = matched.group(1)

	fh = cloudstorage.open(fileobj.filename)
	encodedAlbums = fh.read()
	fh.close()

	owner_list[owner_id] = pickle.loads(encodedAlbums)

    logger.debug("owner_list: " + var_dump(owner_list))

    #-##############-###-############----###--------------------------
    #-POST内容（フォーム）により処理を振り分け（その２）

    if (flask.request.method == 'POST') and ('route_edit' in flask.request.form):

	logger.info("Edit photo delivary root")

	#-##############-###-######---------
	#- route_editフォームからのPOST
	#  登録ボタンが押されていたら、POSTされたFormデータ内容をroute_listに反映

    	logger.debug("request: " + var_dump(flask.request.form))

	if (flask.request.form['action'] == u'登録') :

	    Line_id = flask.request.form['Line_id']

	    if (flask.request.form['owner_id'] == '-') :

		#-##############-###-######---------
		#- 結び付きの解消

		logger.info(u"Remove delivary setting of : " + flask.request.form['Line_name'])

		if 'owner_id' in route_list[Line_id] :
		    del route_list[Line_id]['owner_id']
		if 'album_id' in route_list[Line_id]:
		    del route_list[Line_id]['album_id']
		if 'album_name' in route_list[Line_id]:
		    del route_list[Line_id]['album_name']

	    elif (flask.request.form['new_album'].strip() != ""):

		#-##############-###-######---------
		#- 新規アルバム作成

		logger.info(u"Create new album '{album}' owned by {owner} and assign to {name}".format(
				album=flask.request.form['new_album'],
				owner=flask.request.form['owner_id'], 
				name=flask.request.form['Line_name']))

		credentials = loadCredentials(flask.request.form['owner_id'])
		album_id = createAlbum(credentials, flask.request.form['new_album'])

		route_list[Line_id]['owner_id'] = flask.request.form['owner_id']
		route_list[Line_id]['album_id'] = album_id
		route_list[Line_id]['album_name'] = flask.request.form['new_album']
		route_list[Line_id]['name'] = flask.request.form['Line_name']

		# update owner_list and it's persistent data
		owner_list[flask.request.form['owner_id']][album_id] = flask.request.form['new_album']
		encodedAlbums = pickle.dumps(owner_list[flask.request.form['owner_id']])
		bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
		fileName = bucketName + "/album_" + flask.request.form['owner_id'] + ".pickle"
		fh = cloudstorage.open(fileName, 'w')
		fh.write(encodedAlbums)
		fh.close()

	    else :
		#-##############-###-######---------
		#- アルバム選択（又は付け替え）

		logger.info(u"Assign album '{album}' owned by {owner} to {name}".format(
				album=owner_list[flask.request.form['owner_id']][flask.request.form['album_id']],
				owner=flask.request.form['owner_id'], 
				name=flask.request.form['Line_name']))

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

	route_info = {}

	Line_id = flask.request.form['selected_route']
	selected_owner_id = route_list[Line_id].get('owner_id', '-')
	selected_album_id = route_list[Line_id].get('album_id', '-')

	logger.info(u"Select delivary root setting of {name}".format(name=route_list[Line_id]['name']))
	logger.debug("request: " + var_dump(flask.request.form))

	route_info['Line_id']    = Line_id
	route_info['Line_name']  = route_list[Line_id]['name']
	route_info['owner_id']   = { '-': ('selected' if selected_owner_id == '-' else '') ,  }
	route_info['album_list'] = {}

	for owner_id in owner_list.keys():
	    route_info['owner_id'][owner_id] = 'selected' if owner_id == selected_owner_id else ''

	if (selected_owner_id != '-'):
	    for album_id, album_name in owner_list[selected_owner_id].iteritems():
		isSelected = 'selected' if album_id == selected_album_id else ''
		route_info['album_list'][album_id] = { 'name': album_name, 'selected': isSelected }

	logger.debug("route_info : " +  var_dump(route_info))

	mode = {}
	mode['initial'] = 'disabled'
	mode['route_edit'] = ''
	return flask.render_template('connector_config.html', owner_list=owner_list, route_info=route_info, route_list=route_list, mode=mode);

    elif (flask.request.method == 'POST') and ('raw_album_list' in flask.request.form):

	#::
	#:: 実験ページ
	#::
	logger.info("case of album_list")
	logger.debug(var_dump(flask.request.form))
	owner_id = flask.request.form['google_account']
	endpoint = "https://photoslibrary.googleapis.com/v1/albums"
	params = ( ('pageSize', 50), )

	if ('use_cred' in flask.request.form):
	    credentials = loadCredentials(owner_id)
	    headers = {'Authorization': 'Bearer ' + credentials.token, }
	    response = requests.get(endpoint, params = params, headers = headers)
	else:
	    logger.info("url: " +  endpoint)
	    response = requests.get(endpoint, params = params)

	raw_text = response.text
	logger.debug(raw_text[:500])
	mode = {}
	mode['initial'] = ''
	mode['route_edit'] = 'disabled'
	return flask.render_template('connector_config.html', owner_list=owner_list, raw_text=raw_text, route_list=route_list, mode=mode)

    else:

	logger.debug("draw page")
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
    logger.setLevel(loggingLevel)
    logger.info('in authorize')

    try:
	flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)

	flow.redirect_uri = flask.url_for('oauth2callback', _external = True)
	authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true')
	logger.debug('get authorization url from flow : ' + authorization_url)

    except Exception:
	logger.error("Exception in authorize")
	logger.error(traceback.print_exc())
    
    flask.session['state'] = state

    return flask.redirect(authorization_url)

###----OAuth2認証コールバック----
###
@app.route('/oauth2callback')
def oauth2callback():

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info('in oauth2callback.')

#    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'	# You can activate the line to be able to run at a test environment.
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
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
	logger.info('userId: '+ userId + ' acquired from user profile')
	saveCredentials(userId, credentials)

	albums = getAlbums(userId, credentials)

	if not 'pyonta-album' in albums.values():
	    createAlbum(credentials, 'pyonta-album')
	    albums = getAlbums(userId, credentials)

    except Exception:
	logger.error("Exception in authorization callback")
	logger.error(traceback.print_exc())

    return flask.redirect('config')

###----user profileを取得してUserIdを取り出す----
###
def get_userId(credentials):

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info('in get_userId.')

    url_profile = "https://www.googleapis.com/oauth2/v3/tokeninfo"
    params = ( ('id_token', credentials.id_token), )
    response = requests.get(url_profile, params = params)
    logger.debug("acquired json profile: " + response.text)

    profile = json.loads(response.text)
    mailaddr = profile['email']
    userId = mailaddr.split("@")[0].strip()

    return(userId)

###----credentialをcloudstorageに保存----
###
def saveCredentials(userId, credentials) :

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info('in saveCredentials.')

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    fileName = bucketName + '/cred_' + userId + '.pickle'
    logger.debug('** file name = ' + fileName)

    fh = cloudstorage.open(fileName, 'w')
    fh.write(pickle.dumps(credentials))
    fh.close()


###----credentialをcloudstorageから取り出す----
###
def loadCredentials(userId):

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info('in loadCredenitals.')

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    fileName = bucketName + '/cred_' + userId + '.pickle'
    logger.debug('** file name to be loaded is ' + fileName)

    fh = cloudstorage.open(fileName)
    credentials = pickle.loads(fh.read())
    fh.close()

    if not credentials.valid:			# 期限切れの場合はrefresh要求を行う
	logger.info('credentials must be refresh.')
	import google.auth.transport.requests
	request = google.auth.transport.requests.Request()
	credentials.refresh(request)
	logger.info("refreshed credential acquired: "+ var_dump(credentials))

	fh = cloudstorage.open(fileName, 'w')
	fh.write(pickle.dumps(credentials))
	fh.close()

    return (credentials)

###----credentialが持ち主であるphoto アルバム一覧を取得----
###
def getAlbums(userId, credentials):

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info("in getAlbum")

    url_albumList = "https://photoslibrary.googleapis.com/v1/albums"
    params = ( ('pageSize', 50), )
    headers = {'Authorization': 'Bearer ' + credentials.token, }
    albums = {'-':'<default>'}

    while 1 :
	response = requests.get(url_albumList, params = params, headers = headers)
	logger.debug("response of album list : " + response.text);

	j_albums = json.loads(response.text)

	for entry in j_albums['albums']:
	    albums[entry['id']] = entry['title']

	if 'nextPageToken' not in j_albums:
	    logger.info("next token is not exist")
	    break

	params = ( ('pageSize', 50), ('pageToken', j_albums['nextPageToken']) )

    encodedAlbums = pickle.dumps(albums)

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    fileName = bucketName + "/album_" + userId + ".pickle"
    logger.debug('** file name = ' + fileName)

    fh = cloudstorage.open(fileName, 'w')
    fh.write(encodedAlbums)
    fh.close()

    return(albums)

###----Albumを作成する----
###
def createAlbum(credentials, album_name):

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info(u"in createAlbum name = " + album_name)

    url_createAlbum = "https://photoslibrary.googleapis.com/v1/albums"
    body = { 'album': { 'title': album_name }}

    headers = { 'Authorization': 'Bearer ' + credentials.token, 
    		'Content-Type': 'application/json' }

    logger.debug("request headers = " + var_dump(headers))

    try:
	response = requests.post(url_createAlbum, headers=headers, data = json.dumps(body))

    except Exception:
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())
	message = u"アルバム作成に失敗した。"
	return(-1)

    #:
    #: Check Result
    #:
    _code = response.status_code

    if _code >= 200 and _code <= 299:

	_g_album = json.loads(response.content)
	album_id = _g_album['id']
	logger.info("album create result code : " + str(_code))
	logger.info("album id = " + album_id)

	return(album_id)

    else:
	logger.error("album crreate error : " + str(_code))
	return(-1)


###-------------------------------------------------------------------------------
###	写真登録タスクQueue処理
###-------------------------------------------------------------------------------

###----Queue handler----
###
###	非同期タスク処理（Album登録）
###
@app.route('/workerPhoto', methods=['POST'])
def workerPhoto():

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info("in Photo queue handler")

    logger.debug(var_dump(flask.request.form))
    filename = flask.request.form['file']
    owner_id = flask.request.form['owner_id']
    album_id = flask.request.form['album_id']
    userId   = flask.request.form['Line_id']
    counter  = flask.request.form['counter']
    userName = flask.request.form['userName']

    logger.info("user name : " + userName)

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())

    #:
    #: Search for current stat file
    #:
    f_body, f_ext = os.path.splitext(filename)
    prefixFilter = bucketName + '/photo_queue/' + f_body + '.0'
    files = cloudstorage.listbucket(prefixFilter)
    try:
	stat_fname =  next(iter(files)).filename
	matched = re.search("/photo_queue/(.*)_[0-9]+\.([0-9]+)", stat_fname)
	stat_counter = matched.group(2)
	cloudstorage.delete(stat_fname)
    except StopIteration:
	stat_counter = '0'

    logger.info("retry_count = " + str(stat_counter))
    stat_fnext = bucketName + '/photo_queue/' + f_body + '.' + format(int(stat_counter) + 1, "03d") 

    #:
    #: load credentials
    #:
    try:
	credentials = loadCredentials(owner_id)
    except Exception:
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())
	message = "#" + str(counter) + u"が認証エラーで登録できなかった。もう一度設定からやり直してみて。分からなければ江畑潤に聞いて！"
	fp = cloudstorage.open(stat_fnext, 'w')
	fp.write(message.encode('utf-8'))
	fp.close()
	return  u"auth_error", 500

    #:
    #: setup content
    #:
    try:
	filepath = bucketName + '/photo_queue/' + filename
	fh = cloudstorage.open(filepath, mode='r')
	body = fh.read()

    except Exception:
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())
	message = "#" + str(counter) + u"の登録データを無くしちゃったかも。もう一度もらえないかな。"
	fp = cloudstorage.open(stat_fnext, 'w')
	fp.write(message.encode('utf-8'))
	fp.close()
	return("other error"), 500

    #:
    #: POST content
    #:
    ### rulfetch config: set TIMEOUT = 600s
    from google.appengine.api import urlfetch
    urlfetch.set_default_fetch_deadline(600)

#    logger.debug("type of userName = " + str(type(userName)))		= unicode
#    logger.debug("type of '_' = " + str(type('_')))			= str
#    logger.debug("type of counter = " + str(type(counter)))		= unicode
#    logger.debug("type of f_ext = " + str(type(f_ext)))		= unicode

    requestUrl = 'https://photoslibrary.googleapis.com/v1/uploads'
    headers = { 'Authorization': 'Bearer ' + credentials.token, 
		'Content-Type': 'application/octet-stream',
#		'X-Goog-Upload-File-Name': userName + '_'.decode('utf-8') + counter + f_ext,
		'X-Goog-Upload-File-Name': 'photo_' + counter + f_ext,
		'X-Goog-Upload-Protocol': 'raw'  }

    logger.debug(var_dump(headers))

    try:
	response = requests.post(requestUrl, headers=headers, data=body)

    except Exception:
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())
	message = u"なぜか#" + str(counter) + u"をアルバムに登録できなかった。"
	fp = cloudstorage.open(stat_fnext, 'w')
	fp.write(message.encode('utf-8'))
	fp.close()
	return("other error"), 500

    #:
    #: Check Result
    #:
    _code = response.status_code
    _req_h  = response.request.headers
    _req_b  = response.request.body[:400]
    upload_token = response.content.decode('utf-8')
    logger.debug("request headers : " + var_dump(_req_h))
    logger.debug("request body : " + _req_b)
    logger.info("upload_token : " + upload_token)

    if _code >= 200 and _code <= 299:
	    logger.info("upload completed : " + str(_code))
    else:
	    logger.error("queued task error : " + str(_code))
	    message = u"何度試しても#" + str(counter) + u"をアルバム登録がエラーになるよ。"
	    fp = cloudstorage.open(stat_fnext, 'w')
	    fp.write(message.encode('utf-8'))
	    fp.close()
	    return("enqueue error"), _code

    #:
    #: Create MediaItem of updated content
    #:
    requestUrl = 'https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate'

    headers = { 'Authorization': 'Bearer ' + credentials.token, 
		'Accept': 'application/json',
		'Content-Type': 'application/json' }

    body = { 'newMediaItems': [{'simpleMediaItem': {'uploadToken': upload_token}}], }
    if (album_id != '-'): body['albumId'] = album_id

    logger.debug("mediaItems : " + json.dumps(body))

    try:
	response = requests.post(requestUrl, headers = headers, data = json.dumps(body))

    except Exception:
	logger.error("Exception in queue handler")
	logger.error(traceback.print_exc())
	message = u"なぜか#" + str(counter) + u"をアルバムに登録できなかった。"
	fp = cloudstorage.open(stat_fnext, 'w')
	fp.write(message.encode('utf-8'))
	fp.close()
	return("other error"), 500

    #:
    #: Check Result
    #:
    _code = response.status_code
    newMediaItemResults = json.loads(response.content)
    logger.debug("newMediaItemResults:" + var_dump(newMediaItemResults))

    if _code >= 200 and _code <= 299:
	    cloudstorage.delete(filepath)
	    try:
		cloudstorage.delete(stat_fname)
	    except NameError:
	    	pass

	    logger.info("queued task completed : " + str(_code))
	    return("OK"), _code
    else:
	    logger.error("queued task error : " + str(_code))
	    message = u"何度試しても#" + str(counter) + u"をアルバム登録がエラーになるよ。"
	    fp = cloudstorage.open(stat_fnext, 'w')
	    fp.write(message.encode('utf-8'))
	    fp.close()
	    return("enqueue error"), _code


###----Enqueue entry point----
###
###	サイト外からの登録要求受付⇒同期処理でQueue登録まで実施
###
@app.route('/uploadRequestPoint', methods=['POST'])
def uploadRequestPoint():

    logger = logging.getLogger(__name__)
    logger.setLevel(loggingLevel)
    logger.info("in uploadRequestPoint")

    logger.debug(var_dump(flask.request.form))
    Line_id = flask.request.form['source']
    filename = flask.request.form['filename']

    bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
    routeFile = bucketName + "/sourcelist.json"
    fh = cloudstorage.open(routeFile)
    route_list = json.loads(fh.read())
    fh.close()

    try:
	credentials = loadCredentials(route_list[Line_id]['owner_id'])
    except Exception:
	logger.error("Exception in queue generator")
	logger.error(traceback.print_exc())
	response = flask.make_response(u"認証エラーが起きる。もう一度設定からやり直してみて。分からなければ江畑潤に聞いて！", 500)
	return response

    params = {
	'file' : filename,
	'Line_id' : Line_id,
	'owner_id' : route_list[Line_id]['owner_id'],
	'album_id' : route_list[Line_id]['album_id'],
	'counter'  : flask.request.form['counter'],
	'userName'  : flask.request.form['userName'] }

    try:
	task = taskqueue.add(url='/workerPhoto', queue_name='photo-uploader-queue', params=params)
	logger.info("enqueued : name = " + task.name)

    except Exception:
	logger.error("Exception in uploadRequestPoint")
	logger.error(traceback.print_exc())
	return(u"なぜか受付処理ができない。江畑潤じゃないと直せないかも。"), 500

    return(u"OK")

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
