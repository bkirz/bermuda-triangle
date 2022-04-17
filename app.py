from flask import Flask, flash, request, redirect, url_for, send_file

import io
import simfile
from scroll_normalizer import fixedscroll


app = Flask(__name__)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() == 'ssc'

@app.route("/")
def hello_world():
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <h1>Upload new File</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=sscfile>
      <input type=submit value=Upload>
    </form>
    '''

@app.route("/", methods=["POST"])
def upload_file():
    # check if the post request has the file part
    if 'sscfile' not in request.files:
        return redirect(request.url)

    file = request.files['sscfile']

    # If the user does not select a file, the browser submits an
    # empty file without a filename.
    if file.filename == '':
        return redirect(request.url)

    ssc = simfile.loads(file.stream.read().decode("utf-8"))

    fixedscroll(ssc) # mutates the ssc in-place to normalize its scroll rate across bpm changes
    filename = file.filename.replace('.ssc', '-normalized.ssc')

    return send_file(io.BytesIO(str(ssc).encode("utf-8")), as_attachment=True, download_name=filename)