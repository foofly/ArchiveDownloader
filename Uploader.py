from time import sleep
import requests
import getpass
import os
import sys

def getFiles(directory,extension):
    return [
        f for f in os.listdir(directory) 
        if f.endswith(extension)]

def uploadFile(localFile,filename, dest, token):
    print(f"Uploading {filename}")
    with open(localFile,"rb") as f:
        data = f.read()
    
    headers = {
        "Authorization" : f"Bearer {token}",
        "Dropbox-API-Arg": f'{{"path": "{dest}/{filename}", "mode": "overwrite"}}',
        "Content-Type": "application/octet-stream"
    }

    response = requests.post("https://content.dropboxapi.com/2/files/upload",
                             headers=headers,
                             data=data)

    return response.status_code == 200

root = input("Enter upload directory: ")
dest = input("Enter upload destination:")
accessToken = getpass.getpass("Enter access token:")


while True:
    files = getFiles(root,".pdf")
    for f in files:
        localfile = f"{root}/{f}"
        if uploadFile(localfile,f, dest, accessToken):
            os.remove(localfile)
    print("Sleeping...")
    sleep(60 * 60)