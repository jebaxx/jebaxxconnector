import requests
import os

def uploadToAlbum():

    userId =  'jxxebata'
    albumId = '6536666146903484433'
    targetFile = 'images/DSCF1515-2.JPG'
#    endpoint = 'http://localhost:8080/testEntryPoint/user/' + userId + '/albumid/' + albumId
    endpoint = 'http://localhost:8080/testEntryPoint'

    fh = open(targetFile, 'rb')
#    files = {'uploadfile': ( targetFile, fh, mediaType) ,}
#    headers = { 'Content-Type' : 'image/jpeg'  ,  'Slug': 'abc.jpeg' ,  'Content-Length' : '20' }
    headers = { 'Content-Type':'image/jpeg', 'Content-Length':'26836',  'Slug':'abc.jpg' }
    params = ( ('access_token', 'tokentokentoken'), )

    response = requests.post(endpoint, headers=headers, params=params, data=fh)
    if response.status_code != requests.codes.ok:
        return('file upload error code = ' + str(response.status_code) + '<br>' )

    return

from pprint import pformat
import types

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES =["https://picasaweb.google.com/data/"]

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


#------------------------
# main
#

uploadToAlbum()

