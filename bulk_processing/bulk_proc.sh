#!/bin/bash

#FILES = regex for folder
#PROJECT = project for POST request

for f in $FILES
do
	echo "Processing $f ..."
	curl -X POST -H "Content-Type: application/json" http://localhost:7081/analyze/"$PROJECT"/"$f" > /dev/null
	echo "Done"

done
echo "FINISHED"
