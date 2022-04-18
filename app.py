from flask import Flask, request, redirect, send_file, render_template

import io
import simfile
from scroll_normalizer import fixedscroll


app = Flask(__name__)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() == 'ssc'

@app.route("/")
def index():
    return render_template("index.html")

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

    # It's perhaps bold to assume all ssc files are utf-8 encoded, but I'm
    # not sure of a better alternative.
    input_file_contents = file.stream.read().decode("utf-8")
    ssc = simfile.loads(input_file_contents)

    fixedscroll(ssc) # mutates the ssc in-place to normalize its scroll rate across bpm changes
    filename = file.filename.replace('.ssc', '-normalized.ssc')

    # Again, assume utf-8. This should be safe since the input was assumed to be utf-8
    # and AFAICT simfile preserves encoding.
    output_io = io.BytesIO(str(ssc).encode("utf-8"))

    return send_file(output_io, as_attachment=True, download_name=filename)