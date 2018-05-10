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
###	configページを表示
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

	logger.info("request: " + var_dump(flask.request.form))
 
	#-##############-###-######---------
	#-owner_listフォームからのPOST

	if (flask.request.form['action'] == u'新規登録') :
	    return flask.redirect('authorize')

	elif (flask.request.form['action'] == u'アルバム再取得') :
	    credentials = loadCredentials
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
    #-route_listの読み込み

    fileName = bucketName + "/sourcelist.json"
    fh = cloudstorage.open(fileName)
    route_list = json.loads(fh.read())
    fh.close()

    logger.info("route_list: " + var_dump(route_list))

    #-##############-###-############----###--------------------------
    #-owner_listの読み込み

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

    	logger.info("request: " + var_dump(flask.request.form))
	#-##############-###-######---------
	#-route_editフォームからのPOST

	if (flask.request.form['action'] == u'登録') :

	    #---#---###----------------############
	    #-route_editフォームの内容をroute_listに反映する

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

    	logger.info("request: " + var_dump(flask.request.form))
	#-##############-###-######---------
	#-route_listフォームからのPOST

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
	authorization_url, state = flow.authorization_url(access_type='offline', prompt='select_account', include_granted_scopes='true')
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

    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
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
	saveCredentials(userId, pickle.dumps(credentials))

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

#    try:
    fh = cloudstorage.open(fileName)
    credentials = pickle.loads(fh.read())
    fh.close()
#    except cloudstorage.NotFoundError:
#	import traceback
#    	logger.error("cannot load credentials file in storage")
#	logger.error(traceback.print_exc())

    if not credentials.valid:			# 期限切れの場合はrefresh要求を行う
	import google.auth.transport.requests
	request = google.auth.transport.requests.Request()
	credentials.refresh(request)
	logger.info(var_dump(credentials))

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

    albums = {}
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


###-------------------------------------------------------------------------------###
@app.route('/')
def index():

    body = print_index_table()
    return body

@app.route('/appPage')
def appPage():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.debug("in appPage")

    if 'credentials' not in flask.session:
	return flask.redirect('authorize')

    credentials = pickle.loads(flask.session['credentials'])
    
    body = "credential acquired.<br>--------------------<br>"
    if not credentials.valid:
	body += '----------<br>credential is expired!!!<br>'
	import google.auth.transport.requests
	request = google.auth.transport.requests.Request()
	credentials.refresh(request)

	body += '----------<br>'
	body += var_dump(credentials)

	logger.info(var_dump(credentials))

	flask.session['credentials'] = pickle.dumps(credentials)
	saveCredentials(flask.session['credentials'])

    body += '----------<br>'
    body += '<a href="https://picasaweb.google.com/data/feed/api/user/jxxebata">ALBUM_LIST_URL</a><br><br>'
    body += '<a href="/getAlbum">Album List browsing page</a><br><br>'
    body += '<a href="/get_profile">Get User Profile</a><br><br>'
    body += '<a href="/uploadPict">Upload Photos</a><br><br>'
    body += '<a href="/uploadToAlbum">Upload to PhotoAlbum</a><br><br>'
    body += '<a href="/">GOTO Menu</a>'

    return body

@app.route('/uploadPict')
def uplaodPict():
    return(flask.render_template('upload-picts.html', message="Pyonta is PYONTA!"))

@app.route('/uploadEntryPoint', methods=['POST'])
def uploadEntryPoint():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info("in uplaodEntryPoint")

    if 'img_file' not in flask.request.files:
	return('Unexpected POST data<br>----------<br>' + print_index_table())

    try:
	fileStream = flask.request.files['img_file']
	filename = fileStream.filename

	bucketName = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name())
	filename = bucketName + '/images/' + filename
	logger.info('** destination file = ' + filename)
	fh = cloudstorage.open(filename, 'w')
	file_contents = fileStream.read()

	logger.info('** read pict file info from request')

	fh.write(file_contents)
	fh.close()
	fileStream.close()

    except Exception:
	import traceback
	logger.error("cannot upload photo")
	logger.error(traceback.print_exc())

    return(filename + ' uploaded <br>----------<br>' + print_index_table())

@app.route('/testEntryPoint', methods=['POST'])
def testEntryPoint():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info("in testEntryPoint")

    body = flask.request.stream.read()
    logger.info('body = ' + body)
    return('body = ' + body)

#########################################################
## UPLOAD TO ALBUM
#########################################################
@app.route('/uploadToAlbum')
def uploadToAlbum():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info("in uploadToAlbum")

    userId =  'jxxebata'
    albumId = '6536666146903484433'
    targetFile = 'DSCF2558.JPG'
#    targetFile = 'DSCF1515.JPG'
    imgFilePath = os.environ.get('BUCKET_NAME', '/' + app_identity.get_default_gcs_bucket_name()) + '/images/' + targetFile
    endpoint = 'https://picasaweb.google.com/data/feed/api/user/' + userId + '/albumid/' + albumId
#    endpoint = 'http://localhost:8080/uploadEntryPoint/user/' + userId + '/albumid/' + albumId
#    endpoint = 'http://jebaxxconnector.appspot.com/uploadEntryPoint/user/' + userId + '/albumid/' + albumId

    try:
	credentials = pickle.loads(flask.session['credentials'])
	logger.info("Use the credentials: " + var_dump(pickle.loads(flask.session['credentials'])))
	headers = { 'Content-Type':'image/jpeg', 'Content-Length':str(cloudstorage.stat(imgFilePath).st_size), 'Slug':targetFile }
	params = ( ('access_token', credentials.token), )
	fh = cloudstorage.open(imgFilePath, mode='r')
#	sfh = StringIO.StringIO(fh.read())
#	fh.close()
#	data = {'uploadfile': ( targetFile, cloudstorage.open(imgFilePath), 'image/jpeg') ,}

	response = requests.post(endpoint, headers=headers, params=params, data=fh.read(), timeout=20)
#	sfh.close()
	if response.status_code != requests.codes.ok:
	    return('file upload error code = ' + str(response.status_code) + '<br>----------<br>' + print_index_table())

    except Exception:
	import traceback
	logger.error("cannot upload photo")
	logger.error(traceback.print_exc())
	return('file upload error.<br>----------<br>' + print_index_table())

    return('file uploaded.<br>----------<br>' + print_index_table())

@app.route('/getAlbum')
def getAlbum():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.debug("in getAlbum")

    if 'credentials' not in flask.session:
	return flask.redirect('authorize')

    url_albumList = "https://picasaweb.google.com/data/feed/api/user/jxxebata"
    credentials = pickle.loads(flask.session['credentials'])
    params = ( ('access_token', credentials.token), )

    response = requests.get(url_albumList, params = params)

    import xml.etree.ElementTree
    root = xml.etree.ElementTree.fromstring(response.text.encode('utf-8'))
#    nsmap = {'Atom' : "http://www.w3.org/2005/Atom", 'gphoto' : "http://schemas.google.com/photos/2007"}
    nsmap = {'gphoto' : "http://schemas.google.com/photos/2007", 'Atom' : "http://www.w3.org/2005/Atom"}

    body = ""
    body += "---Album list---<br>"
    for entry in root.findall(".//Atom:entry", nsmap):
	body += "# " + entry.find(".//Atom:title", nsmap).text + " --- " + entry.find(".//gphoto:id", nsmap).text + "<br>"

    return(body)

@app.route('/reproduceCredentials')
def reproduceCredentials():

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.info('in reproduceCredentials')

    try:
	flask.session['credentials'] = loadCredentials()
    except cloudstorage.NotFoundError:
    	logger.info("credentials file not found in the cloudstoarage")
    	return flask.redirect('/authorize')
    except Exception:
	import traceback
    	logger.error("cannot load credentials file in storage")
	logger.error(traceback.print_exc())

    body = 'credentials reproduced.<br>----------<br>'
    body += var_dump(pickle.loads(flask.session['credentials'])) + '<br>'

    return( body + print_index_table())

@app.route('/revoke')
def revoke():

    if 'credentials' not in flask.session:
        return ( 'you need to <a href="/authorize">authorize</a> before testing the code to revoke credentials. ' )

    credentials = pickle.loads(flask.session['credentials'])
    
    revoke = requests.post('https://accounts.google.com/o/oauth2/revoke', 
                                params = {'token': credentials.token},
                                headers = {'content-type': 'application/x-www-form-urlencoded'})
    status_code = getattr(revoke, 'status_code')
    
    if status_code == 200 :
        return('Credentials successfully revoked.<br>----------<br>' + print_index_table())
    else:
	return('An error occured.<br>----------<br>' + print_index_table())

@app.route('/clear')
def clear_credentials():

    if 'credentials' in flask.session:
        del flask.session['credentials']
        
    return ('Credentials have been cleared.<br>----------<br>' + print_index_table())

def credentials_to_dict(credentials):
    return {	'token' : credentials.token,
		'refresh_token' : credentials.refresh_token,
		'token_uri' : credentials.token_uri,
		'client_id' : credentials.client_id,
		'client_secret' : credentials.client_secret,
		'id_token' : credentials.id_token,
		'scopes' : credentials.scopes,
		'expiry' : credentials.expiry
	}

def print_index_table():
        
    return( '<table>' +
        '<tr><td><a href="/appPage">Application Main Page</a></td>' +
        '    <td>Application submit some APIrequest(s) based on authorization.' +
        '      Go through the authorization flow if there are no stored ' +
        '      credentials for the user.</td></tr> ' +
        '<tr><td><a href="/reproduceCredentials">Reproduce credentials</a></td>' +
        '    <td>Load credentials from cloudstorage whitch was saved when the last authentication.</td></tr>' +
        '<tr><td><a href="/authorize">Execute Authentication flow</a></td>' +
        '    <td>Go directly to the authorization flow. If there are stored ' +
        '      credentials, you still might not be prompted to reauthorize  ' +
        '      the application.</td></tr>' +
        '<tr><td><a href="/revoke">Revoke current credentials</a></td>' +
        '    <td>Revoke the access token associated with the current user ' +
        '      session. After revoking credentials, if you go to the test ' +
        '      page, you should see an <code>invalid_grant</code> error.' +
        '</td></tr>' +
        '<tr><td><a href="/clear">Clear Flask session credentials</a></td>' +
        '    <td>Clear the access token currently stored in the user session. ' +
        '      After clearing the token, if you <a href="/test">test the ' +
        '      API request</a> again, you should go back to the auth flow.' +
        '</td></tr></table>'  )


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

###############
## in case execute as a main module
##
if __name__ == '__main__':
    # When running locally, disable OAuthlib's HTTPs verification.
    # ACTION ITEM for developers:
    #     When running in production *do not* leave this option enabled.
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Specify a hostname and port that are set as a valid redirect URI
    # for your API project in the Google API Console.
    #    app.run('jebaxxconnector.appspot.com', 80)
    app.run('localhost', 8080)

