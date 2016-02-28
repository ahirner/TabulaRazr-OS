#!/bin/sh

SERVLET = "server"

ipython nbconvert --to python $1
OFILEP=${1%%ipynb}

rm "$SERVLET"".py"
mv "$OFILEP"".py" "$SERVLET"".py"

nohup python "$SERVLET"".py" &> nohup.out.log&
