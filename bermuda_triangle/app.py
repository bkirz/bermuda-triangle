from flask import Flask, flash, request, redirect, send_file, render_template, make_response

import io
import os
import simfile
import simfile.convert
from .make_mines_fake import make_mines_fake, MakeMinesFakeArgs, SameBeatMineAndNoteError
from .scroll_normalizer import fixedscroll
from pathlib import PurePath


app = Flask(__name__)

stage = os.environ.get('STAGE', 'test')
secret_key = os.environ.get('FLASK_SECRET_KEY')

if stage == 'test':
    secret_key = 'FLASK_SECRET_KEY env var not set'
    print('FLASK_SECRET_KEY env var is unset.')
else:
    assert secret_key is not None


app.secret_key = secret_key


def valid_ssc_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "ssc"


@app.route("/")
def index():
    return redirect("/scroll-normalizer")


@app.route("/scroll-normalizer")
def scroll_normalizer():
    return render_template("scroll-normalizer.html.jinja")


@app.route("/scroll-normalizer", methods=["POST"])
def scroll_normalizer_upload():
    # check if the post request has the file part
    if "sscfile" not in request.files:
        return redirect(request.url)

    file = request.files["sscfile"]

    # If the user does not select a file, the browser submits an
    # empty file without a filename.
    if file.filename == "":
        return redirect(request.url)

    # It's perhaps bold to assume all ssc files are utf-8 encoded, but I'm
    # not sure of a better alternative.
    input_file_contents = file.stream.read().decode("utf-8")
    ssc = simfile.loads(input_file_contents)

    input_filename = PurePath(file.filename)

    # We always want to return an ssc, even if the input is a .sm file,
    # since only .ssc files can contain SCROLL segments.
    if isinstance(ssc, simfile.sm.SMSimfile):
        ssc = simfile.convert.sm_to_ssc(ssc)

    output_filename = str(
        input_filename
            .with_suffix(".ssc")
            .with_stem(input_filename.stem + "-normalized")
    )

    fixedscroll(
        ssc
    )  # mutates the ssc in-place to normalize its scroll rate across bpm changes

    # Again, assume utf-8. This should be safe since the input was assumed to be utf-8
    # and AFAICT simfile preserves encoding.
    output_io = io.BytesIO(str(ssc).encode("utf-8"))

    return send_file(output_io, as_attachment=True, download_name=output_filename)


@app.route("/fake-mines")
def fake_mines():
    return render_template("fake-mines.html.jinja")


@app.route("/fake-mines", methods=["POST"])
def fake_mines_upload():
    # Check if the POST request has the file part
    if "sscfile" not in request.files:
        return redirect(request.url)

    file = request.files["sscfile"]

    # If the user does not select a file,
    # the browser submits an empty file without a filename
    if file.filename == "":
        return redirect(request.url)

    # `simfile` can detect encoding for files on the filesystem,
    # but currently lacks this functionality for in-memory byte streams.
    # Fortunately, SSC files are virtually always encoded in UTF-8.
    input_file_contents = file.stream.read().decode("utf-8")
    ssc = simfile.loads(input_file_contents)
    assert isinstance(ssc, simfile.types.SSCSimfile)

    # Assemble the args object (typically handled by `argparse`)
    args = MakeMinesFakeArgs()
    args.allow_split_timing = request.form.get("allow_split_timing") != None
    args.allow_simultaneous = request.form.get("allow_simultaneous") != None
    args.simfile = file.name or ""
    args.dry_run = False
    args.ignore_sm = False

    try:
        make_mines_fake(ssc, args)
    except SameBeatMineAndNoteError as e:
        flash(str(e))
        return redirect(request.url)

    filename = (file.filename or "file.ssc").replace(".ssc", "-fakemines.ssc")

    # Again, UTF-8 here is an assumption
    output_io = io.BytesIO(str(ssc).encode("utf-8"))

    return send_file(output_io, as_attachment=True, download_name=filename)
