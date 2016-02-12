
import ConfigParser
import gc
import glob
import io
import os
import cStringIO
import re
import subprocess
import string
import sys
import numpy as np
import pandas as pd

def GetConfigParm(section):
	dict1 = {}
	options = Config.options(section)
	for option in options:
		try:
			dict1[option] = Config.get(section, option)
			if dict1[option] == -1:
				DebugPrint("skip: %s" % option)
		except:
			print("exception on %s!" % option)
			dict1[option] = None
	return dict1

# Main Process
# Read Configuration Parameters
config = ConfigParser.RawConfigParser()
config.read('GetMuniBondData.cfg')
OutputFileName = config.get("FileLocations","OutputFileName")
OutputColumnSeparator = config.get("FileLocations","OutputColumnSeparator")
InputPath = config.get("FileLocations","InputPath")

# Initialize Data Frame
df = pd.DataFrame(np.zeros(0 , dtype=[('file', 'a99'),('caption', 'a99'),('value', 'a99')]))

for file in glob.glob(InputPath):

	printline = 0
	linesleft = 0
	blanklines = 0

	intxtfilename = file + ".txt"

	out, err = subprocess.Popen(["pdftotext", "-layout", file, file + ".txt" ]).communicate()
	   
	try:	
	   intxtfile = io.open(intxtfilename, mode='rb')
	except:
	   print "Unable to extract text from " + file
	   continue

	lines = intxtfile.readlines()

	topfound = 0
	headerline = 0
        
	for line in lines:

		strippedline = line.upper().strip()

		if topfound == 0 and string.find(line,"       $") > 0:
			headerline = 1
			topfound = 1
	   
		if 1 <= headerline <= 3:
			caption = "HEADER " + str(headerline)
			value = strippedline
			df = df.append({'file':file, 'caption':caption, 'value':value},ignore_index=True)
			headerline = headerline + 1
			continue
	       
		if strippedline == "SOURCES AND USES OF FUNDS" \
		or strippedline == "SOURCES AND USES OF FUNDS*" \
		or strippedline == "ESTIMATED SOURCES AND USES OF FUNDS" \
		or strippedline == "ESTIMATED SOURCES AND USES OF FUNDS*" \
		or strippedline == "SOURCES AND USES OF FUNDS(1)" \
		or strippedline == "ESTIMATED SOURCES AND USES OF FUNDS(1)" \
		or strippedline == "PLAN OF FINANCE AND ESTIMATED SOURCES AND USES OF FUNDS":
			printline = 1
			linesleft = 25
		
		if printline == 1:
			dollar_amount_regex = re.compile("[\$]{0,1}[\s]{0,6}[0-9,]{0,15}(\.[0-9]{1,2})$")
			dollar_amount_match = re.search(dollar_amount_regex,strippedline)
			if dollar_amount_match:
				caption = strippedline[:dollar_amount_match.start(0)].strip()
				value = strippedline[dollar_amount_match.start(0):].strip()
				df = df.append({'file':file, 'caption':caption, 'value':value},ignore_index=True)
			if len(line.strip()) < 5 and linesleft < 10:
				blanklines = blanklines + 1
			linesleft = linesleft - 1
		 
		if linesleft == 0:
			printline = 0

	del lines
	gc.collect()

df.to_csv(OutputFileName,OutputColumnSeparator,index=False)
