#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
*****************************************************************************
LIRIS object annotation tool

Authors: Christian Wolf, Eric Lombardi, Julien Mille

#BEGCUT
Changelog:

10.09.14 el: - Fix performance issue (slow-down when first rectangles are drawn). 
03.09.14 el: - Replace 'moving arrows' image by a circle around anchor points, to provide better 
               visibility in small boxes ; change anchor points activation distance to allow
               smaller boxes.
03.09.14 el: - Changing the classes is made easier: it only requires to modify the 'classnames' 
               variable ; the class menu is now dynamically built from the content of the 
               'classnames' variable, and does'nt need anymore to be changed by hand.  
14.12.11 cw: - Bugfix in actreader version : remove imgTrash and imgMove and
               references to it
01.12.11 cw: - Added comments allowing to extract a read only version of the tool
06.10.11 cw: - Change the description of some objects
             - Check if save went ok
             - Jump only 25 frames
             - The program does not stop when no objects are in an existing XML file
             - A loaded file is not automatically considered as modified
05.10.11 cw: - Check whether the XML frame numbers are larger than the 
               number of frames in the input
             - Remove most of the debugging output
03.10.11 cw: - Added "D" (DELETE ALL) command
             - Runid's can be entered with the keyboard
             - Typing in a videoname will do keyboard short cuts (d,f etc.)
             - Check for validity when saving a file
             - Jump far with page keys
             - Check for unsaved changes before quitting
             - Add video length in the title
01.19.11 cw: - Added "d" (DELETE) command
             - Simulate right click with CTRL + left Click
             - Bugfixes:
             -- All 4 corners can be used to resize a rectangle now
29.09.11 el: Integration du module tracking de Julien Mille
07.09.11 cw: Bugfixes:
             -no crash if XML does not exist
             -correct update of class list; 
             -fixed: incomplete XML export
             -fixed: Propagating with space after listbox usage will pop up the listbox again
             -Short click on the image will create a rectangle with weird coordinates
30.08.11 cw: Add XML parser
02.07.11 cw: begin development

List of known bugs:
#ENDCUT
*****************************************************************************
"""

from Tkinter import Tk, Canvas, Frame, BOTH, Listbox, Toplevel, Message, Button, Entry, Scrollbar, Scale, IntVar
from Tkinter import N,S,W,E,NW, SW, NE, SE, CENTER, END, LEFT, RIGHT, X, Y, TOP, BOTTOM, HORIZONTAL
import Image
import ImageDraw
import ImageFont
import ImageTk
import sys, glob, copy
import tkMessageBox
import os
import xml.etree.ElementTree as xml

import matplotlib.image as mpimg
import numpy as np

#BEGCUT
from minimal_ctypes_opencv import *
#ENDCUT

# ***************************************************************************
# Global constants
# ***************************************************************************

MAX_RUNID = 100
CORNER_DIST_THR=8
CENTER_DIST_THR=10
CORNER_SIZE=30
CENTER_SIZE=30
JUMP_FRAMES=25
TITLE = "LIRIS-HARL object reader V1.01"
#BEGCUT
TITLE = "LIRIS-HARL object annotation tool V1.0"
#ENDCUT

# ***************************************************************************
# The data structure storing the annotations
# ***************************************************************************

# change the list below to define your own classes
#classnames = ["head","fullbody","right-hand","left-hand"]
classnames = ["bag", "bike", "car", "chair", "computer", "keyboard", "person", "phone", "screen", "shelf", "table","null"]
# ***************************************************************************
# XML parsing helper functions
# ***************************************************************************

# Return the the given tag in the given tree, and ensure that this tag is 
# present only a single time. 
def getSingleTag(tree,tagname):
    rv=tree.findall(tagname)
    if len(rv)!=1:
        tkMessageBox.showinfo(TITLE, "tag "+tagname+" needs to occur a single time at this point!")
        sys.exit(1)
    return rv[0] 

# Return an attribute value. Check for its existence
def getAtt(node,attname):
    rv=node.get(attname)
    if rv==None:
        tkMessageBox.showinfo(TITLE, "attribute "+attname+" not found in tag "+node.tag)
        sys.exit(1)
    return rv

# ***************************************************************************
class AARect:
    """A rectangle (bounding box) and its running id"""
    def __init__(self,x1,y1,x2,y2,runid):
        if x1<x2:
            self.x1=x1
            self.x2=x2
        else:
            self.x1=x2
            self.x2=x1
        if y1<y2:
            self.y1=y1	
            self.y2=y2
        else:
            self.y1=y2	
            self.y2=y1
        self.runid=runid
        
    def show(self):
        print "x1=", self.x1, "  y1=", self.y1, "  x2=", self.x2, "  y2=", self.y2, "  id=", self.runid

#BEGCUT
# ***************************************************************************
# C type matching Python type
class c_AARect(ctypes.Structure):
   	_fields_ = [ ("x1", ctypes.c_int), 
   	             ("y1", ctypes.c_int), 
   	             ("x2", ctypes.c_int),
   	             ("y2", ctypes.c_int),
   	             ("runid", ctypes.c_int) ]

# ***************************************************************************
# convert AARect to c_AARect
def to_c_AARect(r):
	return c_AARect( x1=int(r.x1), y1=int(r.y1), x2=int(r.x2), y2=int(r.y2), runid=int(r.runid))

# ***************************************************************************
# convert c_AARect to AARect
def to_AARect(c_r):
	return AARect( c_r.x1, c_r.y1, c_r.x2, c_r.y2, c_r.runid)
#ENDCUT


# ***************************************************************************
class SemMousePos:
    """A semantic mouse position: in which rectangle (index) is the mouse
       and which semantic position does it occupy.
       sempose can be:
       ul	upper left corner
       ur	upper right corner
       ll	lower left corner
       lr	lower right corner
       c	center
       g	general position in the recangle
       n	no rectangles"""
    def __init__(self,index,sempos):
        self.index=index
        self.sempos=sempos          

# ***************************************************************************
class AAFrame:
    """All rectangles of a frame"""
    def __init__(self):
        self.rects=[]
	
    def getRects(self):
        return self.rects
	
    # Check the position of the mouse cursor with respect to corners of all
    # the rectangles, as well as the centers. If it is not near anything, 
    # still check for the nearest center.
    # position x,y
    def getSemMousePos(self,x,y):

        # First check for the corners
        minval=99999999
        argindex=-1	
        for (i,r) in enumerate(self.rects):	    
            d=(r.x1-x)*(r.x1-x)+(r.y1-y)*(r.y1-y)
            if d<minval:
                minval=d
                argindex=i
                argsem="ul"
            d=(r.x1-x)*(r.x1-x)+(r.y2-y)*(r.y2-y)
            if d<minval:
                minval=d
                argindex=i
                argsem="ll"
            d=(r.x2-x)*(r.x2-x)+(r.y1-y)*(r.y1-y)
            if d<minval:
                minval=d
                argindex=i
                argsem="ur"
            d=(r.x2-x)*(r.x2-x)+(r.y2-y)*(r.y2-y)
            if d<minval:
                minval=d
                argindex=i
                argsem="lr"
            
        # We near enough to a corner, we are done
        if minval<CORNER_DIST_THR*CORNER_DIST_THR:
            return SemMousePos(argindex,argsem)
            
        # Now check for the nearest center
        minval=99999999
        argindex=-1
        for (i,r) in enumerate(self.rects):
            cx=0.5*(r.x1+r.x2)
            cy=0.5*(r.y1+r.y2)
            d=(cx-x)*(cx-x)+(cy-y)*(cy-y)
            if d<minval:
                minval=d
                argindex=i
        
        if argindex<0:
            return SemMousePos(-1,"n");
        
        if minval<CENTER_DIST_THR*CENTER_DIST_THR:
            return SemMousePos(argindex,"c")
        else:
            return SemMousePos(argindex,"g")	

# ***************************************************************************
class AAControler:            
    def __init__(self):
        # An array holding an AAFrame object for each frame of the video
        self.frames=[]	
        # An array holding the classnr for each object nr. ("runid")
        self.runids=[]
        # The nr. of the currently visible frame
        self.curFrameNr=0
        self.videoname=""
        if len(sys.argv)!=3:
            self.usage()
        prefix=sys.argv[1]
        self.outputfilename=sys.argv[2]
        self.filenames=sorted(glob.glob(prefix+"*"))
        # print self.filenames
        if len(self.filenames)<1:
            print >> sys.stderr, "Did not find any frames! Is the prefix correct?"
            self.usage()
        for i in range(len(self.filenames)):
            self.frames.append(AAFrame())
            
        # If the given XML file exists, parse it
        if os.path.isfile(self.outputfilename):
            self.parseXML()
        else:
        
            # If it does NOT exist, let's try to create one
            try:
                fd=open(self.outputfilename,'w')
                
            # Unsuccessful -> the given directory does not exist
            except:
                s="Could not save to the specified XML file. Please check the location. Does the directory exist?"
                tkMessageBox.showinfo(TITLE,s)
                sys.exit(1)
            tkMessageBox.showinfo(TITLE, "XML File "+self.outputfilename+" does not exist. Creating a new one.")
        
    def usage(self):
        print >> sys.stderr, "usage:"
        print >> sys.stderr, sys.argv[0],"<framefileprefix> <output-xml-filename>"
        sys.exit(1);
    
    # Check the current annotation for validity
    def checkValidity(self):
        msg=''
    
        # Check for non contiguous activities.
        # Keep a dictionary which holds for each activity the framenr of the
        # last frame
        acts = {}
        for (frnr,fr) in enumerate(self.frames):
            for r in fr.rects:
                if r.runid in acts:
                    if frnr-acts[r.runid] > 1:
                        msg = msg+"Activity nr. "+str(r.runid)+" has a hole after frame nr. "+str(acts[r.runid])+".\n"
                acts[r.runid] = frnr;
                    
        # Check for several occurrences of a runid in the same frame.
        for (frnr,fr) in enumerate(self.frames):
            msg=msg+self.checkValidityFrame(frnr)
        
        # Check for unassigned runids (no known object class)
        msg2=''
        for (i,x) in enumerate(self.runids):
            if x<0:
                msg2=msg2+str(i+1)+","
        if msg2<>'':
            msg2="The following activities do not have assigned classes: "+msg2+"\n"
        msg=msg+msg2    
            
        return msg 
        
    # Check a single frame for validity (multiple identical runids)    
    def checkValidityFrame(self, framenr):
        msg=''
        ids=set()
        for r in self.frames[framenr].rects:
            if r.runid in ids:
                msg = msg+'Activity nr. '+str(r.runid)+' occurs multiple times in frame nr. '+str(framenr)+'.\n'
            else:
                ids.add(r.runid)
        return msg

    # Open the image corresponding to the current frame number,
    # set the property self.curImage, and return it
    def curFrame(self):
	name,ext=os.path.splitext(self.filenames[self.curFrameNr])
	if ext == ".png":
		#png = Image.open(self.filenames[self.curFrameNr])#.convert('L')
		img_matplotlib=mpimg.imread(self.filenames[self.curFrameNr])
		value_max = np.amax(img_matplotlib)
		scale = 254. / value_max
		png = Image.fromarray(np.uint8((img_matplotlib)*scale))
		print(40*"-")
		print "format :",png.format
		print "size :", png.size
		print "mode :", png.mode
		#png.load()
		data = list(png.getdata())
		print "max(data)", max(data),"min(data)", min(data)
		self.curImage = png
	elif ext == ".jpg":
        	self.curImage = Image.open(self.filenames[self.curFrameNr])
	else:
		print "Extension not supported but trying anyway. [",ext,"]"
        	self.curImage = Image.open(self.filenames[self.curFrameNr])
       	# print "frame nr. ",self.curFrameNr, "=",self.filenames[self.curFrameNr]
        return self.curImage
    
    # Remove all rectangles of the current frame
    def deleteAllRects(self):
        self.frames[self.curFrameNr].rects = []
      
    # Remove the rectangle with the given index from the list
    # of rectangles of the currently selected frame
    def deleteRect(self, index):
        del self.frames[self.curFrameNr].rects[index];
     
    def nextFrame(self,doPropagate,force):                    
        if self.curFrameNr<len(self.filenames)-1:
            self.curFrameNr+=1        
        # if the next frame does NOT contain any rectangles, 
        # propagate the previous ones
        if doPropagate:
            x=len(self.frames[self.curFrameNr].rects)
#BEGCUT            
            print "we have",x,"frames"          
            if x>0 and not force :
                print "No propagation, target frame is not empty"
            else:
                self.frames[self.curFrameNr].rects = []                
                y = len(self.frames[self.curFrameNr-1].rects)
                if y>0:
                    # Tracking code goes here .....
                    print "Propagating ",y,"rectangle(s) to next frame"
                    
                    if trackingLib == None:
                        # simple copy
                        print "simple copy"
                        self.curFrame()
                        self.frames[self.curFrameNr].rects = copy.deepcopy(self.frames[self.curFrameNr-1].rects)
                    else:
                        # JM tracking
                        print "use JM tracking"                      
                        self.oldFrame = self.curImage
                        self.curFrame()
                        
                        for inrect in self.frames[self.curFrameNr-1].rects:
                            # convert PIL image to OpenCV image
                            cvOldImg = cvCreateImageFromPilImage(self.oldFrame) 
                            cvCurImg = cvCreateImageFromPilImage(self.curImage) 
                            # No need to invoke cvRelease...()

                            # convert Python types to C types
                            c_inrect = to_c_AARect(inrect)
                            c_outrect = c_AARect()

                            # call C++ tracking lib
                            trackingLib.track_block_matching( ctypes.byref(cvOldImg), ctypes.byref(cvCurImg), ctypes.byref(c_inrect), ctypes.byref(c_outrect))

                            # convert C types to Python types
                            outrect = to_AARect(c_outrect)
                            self.frames[self.curFrameNr].rects.append(outrect)

                else:
                    print "No frames to propagate"
#ENDCUT                    
        else:
            self.curFrame()
        self.exportXMLFilename("save.xml")
        return self.curImage

    def nextFramePropCurrentRect(self,rect_index):       
		propagateId = self.frames[self.curFrameNr].rects[rect_index].runid
		print "Rect[",rect_index,"].runid == ",  propagateId

		if self.curFrameNr<len(self.filenames)-1:
			self.curFrameNr+=1     

	   
	    	print "Propagating rectangle",propagateId," to new frame"
		x = len(self.frames[self.curFrameNr].rects)
		y = len(self.frames[self.curFrameNr-1].rects)
	    	print "we have ",x," objects"      
	    	print "we had  ",y," objects"          

		#self.frames[self.curFrameNr].rects = []           
	
		# get old rect to propagate
		rectToPropagate = self.frames[self.curFrameNr-1].rects[rect_index]

		# get his new position by tracking
	    	if trackingLib == None:
			# simple copy
			print "simple copy"
			self.curFrame()
			rectPropagated = copy.deepcopy(rectToPropagate)
	    	else:
			# JM tracking
			print "use JM tracking"                      
			self.oldFrame = self.curImage
			self.curFrame()
	

			# convert PIL image to OpenCV image
			cvOldImg = cvCreateImageFromPilImage(self.oldFrame) 
			cvCurImg = cvCreateImageFromPilImage(self.curImage) 
			# No need to invoke cvRelease...()

			# convert Python types to C types
			c_inrect = to_c_AARect(rectToPropagate)
			c_outrect = c_AARect()

			# call C++ tracking lib
			trackingLib.track_block_matching( ctypes.byref(cvOldImg), ctypes.byref(cvCurImg), ctypes.byref(c_inrect), ctypes.byref(c_outrect))

			# convert C types to Python types
			rectPropagated = to_AARect(c_outrect)
			#self.frames[self.curFrameNr].rects.append(outrect)
	
		rectPropagated.runid = propagateId

		# update it or add it
		rectAlreadyExists = False
		for i,currentrect in enumerate(self.frames[self.curFrameNr].rects):
			if currentrect.runid == propagateId:
				print "Rectangle found. Updating."
				self.frames[self.curFrameNr].rects[i] = copy.deepcopy(rectPropagated)
				rectAlreadyExists = True
				break
	
		if not rectAlreadyExists:
			self.frames[self.curFrameNr].rects.append(rectPropagated)
	    
		#self.curFrame()
		self.exportXMLFilename("save.xml")
		return self.curImage  
    
    def changeFrame(self, id_frame):
        self.curFrameNr=int(id_frame)-1
        self.exportXMLFilename("save.xml")
        return self.curFrame() 
    
    def nextFrameFar(self):
        if self.curFrameNr<len(self.filenames)-JUMP_FRAMES:
            self.curFrameNr+=JUMP_FRAMES 
        else:
            self.curFrameNr=len(self.filenames)-1
        self.exportXMLFilename("save.xml")
        return self.curFrame()
	
    def prevFrame(self):
        if self.curFrameNr>0:
            self.curFrameNr-=1
        self.exportXMLFilename("save.xml")
        return self.curFrame()  
        
    def prevFrameFar(self):
        if self.curFrameNr>=JUMP_FRAMES:
            self.curFrameNr-=JUMP_FRAMES
        else:
            self.curFrameNr=0
        self.exportXMLFilename("save.xml")
        return self.curFrame()  
                
    def getRects(self):	
        return self.frames[self.curFrameNr].getRects()
	
    def addRect(self,x1,y1,x2,y2,runid,fnr=-1):
        if fnr==-1:
            fnr=self.curFrameNr
        if fnr>=len(self.frames):
            raise Exception()
        self.frames[fnr].getRects().append(AARect(x1,y1,x2,y2,runid))
	
    def delRect(self,index):	
        del self.frames[self.curFrameNr].getRects()[index]
	
    def getSemMousePos(self,x,y):
        return self.frames[self.curFrameNr].getSemMousePos(x,y)
	    			
	# Update the running id for a rectangle index
    def updateRunId(self,indexRect,newId):        
        self.frames[self.curFrameNr].rects[indexRect].runid=newId	
        self.useRunId(newId)
        
    # Tell the system the given runId is used. If the array holding the classes 
    # for the different ids is not large enough, grow it and insert -1 as class
    def useRunId(self,newId):
        neededcap=newId-len(self.runids)
        if neededcap>0:
            for i in range(neededcap):
                self.runids.append(-1)
        print "new run id array",self.runids
        
    def exportXML(self):
        self.exportXMLFilename(self.outputfilename)
	
    def exportXMLFilename(self,filename):
        # Get maximum running id 
        maxid=-1
        for (i,f) in enumerate(self.frames):
            for (j,r) in enumerate(f.getRects()):
                if r.runid > maxid:
                    maxid=r.runid
        
        try:
            fd=open(filename,'w')
        except:
            tkMessageBox.showinfo(TITLE, "Could not save to the specified XML file. Please check the location. Does the directory exist?")
        print >> fd, "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        print >> fd, "<tagset>"
        print >> fd, "  <video>"
        print >> fd, "    <videoName>"+self.videoname+"</videoName>"
        


	#self.filenames[self.curFrameNr]
        # Travers all different running id's 
        for currunid in range(maxid):
            foundRects=False
            for (i,f) in enumerate(self.frames):
                for (j,r) in enumerate(f.getRects()):
                    if r.runid==currunid+1:
                        if not foundRects:
                            foundRects=True
                            fd.write ("    <object nr=\""+str(currunid+1)+"\" class=\""+str(self.runids[currunid])+"\">\n")	
                        s="      <bbox x=\""+str(int(r.x1))+"\" y=\""+str(int(r.y1))
                        s=s+"\" width=\""+str(int(r.x2-r.x1+1))+"\" height=\""+str(int(r.y2-r.y1+1))
                        s=s+"\" framenr=\""+str(i+1)
                        s=s+"\" framefile=\""+self.filenames[i]+"\"/>\n"
                        fd.write(s)
            if foundRects:
                print >> fd, "    </object>"	    	    
        print >> fd, "  </video>"  
        print >> fd, "</tagset>"  
        fd.close()
        
    def parseXML(self):
        tree = xml.parse(self.outputfilename)
        rootElement = tree.getroot()
        
        # Get the single video tag
        vids=tree.findall("video")
        if len(vids)<1:
            tkMessageBox.showinfo(TITLE, "No <video> tag found in the input XML file!")
            sys.exit(1)
        if len(vids)>1:
            tkMessageBox.showinfo(TITLE, "Currently only a single <video> tag is supported per XML file!")
            sys.exit(1)
        vid=vids[0]
        
        # Get the video name
        x=getSingleTag(vid,"videoName")            
        if (x.text is None) or (len(x.text)==0) or (x.text=="NO-NAME"):
            tkMessageBox.showinfo(TITLE, "The video name in the given XML file is empty. Please provide the correct name before saving the file.")
            self.videoname="NO-NAME"
        else:
            self.videoname=x.text        
        
        # Get all the objects
        objectnodes=vid.findall("object")
        if len(objectnodes)<1:
            tkMessageBox.showinfo(TITLE, "The given XML file does not contain any objects.")
        for a in objectnodes:
            # Add the classnr to the runid array. Grow if necessary
            anr=int(getAtt(a,"nr"))
            aclass=int(getAtt(a,"class"))
            # print "-----",anr,aclass
            # print len(self.runids)
            if len(self.runids)<anr:
                # print "Growing runid:"
                self.runids += [None]*(anr-len(self.runids))            
            self.runids[anr-1]=aclass
            # print "size of runid array:", len(self.runids), "array:", self.runids    
            
            # Get all the bounding boxes for this object
            bbs=a.findall("bbox")
            if len(bbs)<1:
                tkMessageBox.showinfo(TITLE, "No <bbox> tags found for an object in the input XML file!")
                sys.exit(1)
            for bb in bbs:
                
                # Add the bounding box to the frames() list
                bfnr=int(getAtt(bb,"framenr"))
                bx=int(getAtt(bb,"x"))
                by=int(getAtt(bb,"y"))
                bw=int(getAtt(bb,"width"))
                bh=int(getAtt(bb,"height"))
                try:
                    self.addRect(bx,by,bx+bw-1,by+bh-1,anr,bfnr-1)
                except:
                    print "*** ERROR ***"
                    print "The XML file contains rectangles in frame numbers which are outside of the video"
                    print "(frame number too large). Please check whether the XML file really fits to these"
                    print "frames."
                    sys.exit(1)

# ***************************************************************************
# GUI
# The state variable self.state can take one of the following values:
# ul 	we are currently moving the upper left corner
# ur 	we are currently moving the upper right corner
# ll 	we are currently moving the lower left corner
# lr 	we are currently moving the lower right corner
# c 	we are currently moving the window
# d	we are currently drawing a new rectangle
# i	we are currently choosing the running id
# "" 	(empty) no current object
# ***************************************************************************

class Example(Frame):

    def __init__(self, parent, aCurPath):
        Frame.__init__(self, parent)            
        self.parent = parent     
        self.curPath = aCurPath
        self.ct = AAControler();        
        fontPath = os.path.dirname(os.path.realpath(__file__))
        self.imgFont = ImageFont.truetype(fontPath + "/FreeSans.ttf", 30)
        self.initUI()
        self.eventcounter = 0
    
    # Interface startup: create all widgets and create key and mouse event
    # bindings
    def initUI(self):      
        self.parent.title(TITLE+" (frame nr.1 of "+str(len(self.ct.filenames))+")")        
        self.pack(fill=BOTH, expand=1)                
        self.img = self.ct.curFrame()
        self.curFrame = ImageTk.PhotoImage(self.img)
        
        self.imgTrash = ImageTk.PhotoImage(Image.open(self.curPath+"/trashcan.png"))
        self.imgMove = ImageTk.PhotoImage(Image.open(self.curPath+"/move.png"))
       

	# create canvas
        self.canvas = Canvas(self.parent, width=self.img.size[0], height=self.img.size[1])
        
	#create scale bar
	self.scalevar = IntVar()
	self.xscale = Scale(self.parent,variable = self.scalevar,from_=1, to=len(self.ct.filenames), orient=HORIZONTAL, command=self.changeFrame)


	self.canvas.create_image(0, 0, anchor=NW, image=self.curFrame)  


                            
        self.runidbox = Listbox(self.parent)
        self.savebutton = Button(self.parent, text="SAVE")
        self.quitbutton = Button(self.parent, text="QUIT")
        self.fnEntry = Entry(self.parent)
        self.grid(sticky=W+E+N+S)

	# position
        self.canvas.grid(row=0,column=0,rowspan=4)
        self.runidbox.grid(row=0,column=1,sticky=N+S)
        self.fnEntry.grid(row=1,column=1)
        self.savebutton.grid(row=2,column=1)
        self.quitbutton.grid(row=3,column=1)
        self.xscale.grid(row=4,sticky=W+E)


        # Bindings - for both versions               
        self.canvas.bind ("<Key-Left>", self.prevFrame)
        self.canvas.bind ("<Key-BackSpace>", self.prevFrame)
        self.canvas.bind ("<Key-Right>", self.nextFrame)        
        self.canvas.bind ("<Next>", self.nextFrameFar)
        self.canvas.bind ("<Prior>", self.prevFrameFar)   # the space key
        self.quitbutton.bind("<Button-1>", self.quit) 
        self.canvas.bind ("<Motion>", self.mouseMove)
 
#BEGCUT
        # Bindings for the editor only
        self.canvas.bind ("<Button-1>", self.leftMouseDown)
        self.canvas.bind ("<ButtonRelease-1>", self.leftMouseUp)	
        self.canvas.bind ("<Button-3>", self.rightMouseDown)
        self.canvas.bind ("<ButtonRelease-3>", self.rightMouseUp)
        self.canvas.bind ("q", self.quit)
        self.canvas.bind ("s", self.saveXML)
        self.canvas.bind ("f", self.nextFrameWPropForced)
        self.canvas.bind ("p", self.nextFrameWPropForcedSelectedRect)
        self.canvas.bind ("d", self.deleteCurRect)
        self.canvas.bind ("D", self.deleteAllRects)
        self.canvas.bind ("1", self.choseRunId1)
        self.canvas.bind ("2", self.choseRunId2)
        self.canvas.bind ("3", self.choseRunId3)
        self.canvas.bind ("4", self.choseRunId4)
        self.canvas.bind ("5", self.choseRunId5)
        self.canvas.bind ("6", self.choseRunId6)
        self.canvas.bind ("7", self.choseRunId7)
        self.canvas.bind ("8", self.choseRunId8)
        self.canvas.bind ("9", self.choseRunId9)
        self.canvas.bind ("0", self.choseRunId10)
        self.runidbox.bind ("<Key-space>", self.nextFrameWProp)   # the space key   
        self.canvas.bind ("<Key-space>", self.nextFrameWProp)   # the space key
        self.runidbox.bind ("<<ListboxSelect>>", self.runidboxClick)        
        self.savebutton.bind("<Button-1>", self.saveXML)
        
#ENDCUT        
        
        # Variable inits
        self.state=""
        self.mousex = 1
        self.mousey = 1
        self.runIdProposed4NewRect=1
        self.displayAnno()
        self.displayRunIds()
        self.fnEntry.delete(0, END)
        self.fnEntry.insert(0, self.ct.videoname)
        self.isModified=False
        self.canvas.focus_force()
        
    def checkValidity(self):
        msg=self.ct.checkValidity()
        if len(self.fnEntry.get())<1:
            msg=msg+"The video name is empty.\n"
        if len(msg)>0:
            tkMessageBox.showinfo(TITLE, "There are errors in the annotation:\n\n"+msg+"\nThe file has been saved. Please address the problem(s) and save again.")    
        
    def quit(self,event):        
        print "quit method"
        self.ct.videoname=self.fnEntry.get()

        ok=True
#BEGCUT                
        if self.isModified:
            if tkMessageBox.askyesno( title='Unsaved changes', message='The annotation has been modified. Do you really want to quit?'):
                tkMessageBox.showinfo ("First help","A backup of the latest changes can be found in save.xml, just in case.")            
            else:
                ok=False
                
#ENDCUT                
        if ok:
#BEGCUT        
        
            # close tracking library
            if trackingLib != None:
                trackingLib.close_lib() 
#ENDCUT                
            self.parent.destroy()


    def updateAfterJump(self):
        self.curFrame = ImageTk.PhotoImage(self.img)
        self.displayAnno()        
        self.parent.title(TITLE+" (frame nr."+str(self.ct.curFrameNr+1)+" of "+str(len(self.ct.filenames))+")")  
        self.canvas.update()
    def changeFrame(self,id_frame):
        self.img = self.ct.changeFrame(id_frame)
        self.updateAfterJump()
   
    def prevFrame(self,event):
        self.img = self.ct.prevFrame()
        self.updateAfterJump()
        
    def prevFrameFar(self,event):
        self.img = self.ct.prevFrameFar()
        self.updateAfterJump()
                
    def nextFrame(self,event):
        self.img = self.ct.nextFrame(False, False)
        self.updateAfterJump()
        
    def nextFrameFar(self,event):
        self.img = self.ct.nextFrameFar()
        self.updateAfterJump()
                
    def nextFrameWProp(self,event):        
        self.img = self.ct.nextFrame(True, False)
        self.updateAfterJump()
        self.isModified=True
        
    def nextFrameWPropForced(self,event):        
        self.img = self.ct.nextFrame(True, True)
        self.updateAfterJump()
        self.isModified=True

    def nextFrameWPropForcedSelectedRect(self,event):
        sempos = self.ct.getSemMousePos(self.mousex,self.mousey)
        if sempos.index > -1:
            self.img = self.ct.nextFramePropCurrentRect(sempos.index)
	    self.updateAfterJump()
	    self.isModified=True
        
    def mouseMove(self,event):
        #self.debugEvent('mouseMove')

        self.displayAnno()
        self.mousex = event.x
        self.mousey = event.y

 	maxx = self.img.size[0]
	maxy = self.img.size[1]

	#print "mouse x,y = ",self.mousex,",",self.mousey
        
        # Put the focus on the canvas, else the other widgets 
        # keep all keyboard events once they were selected.
        self.canvas.focus_force()

#BEGCUT  

        if self.state=="d":
            # We currently draw a rectangle
            self.curx2=min(maxx,max(1,event.x))
            self.cury2=min(maxy,max(1,event.y))	    
            self.canvas.create_rectangle(self.curx1, self.cury1, self.curx2, self.cury2,
                outline="blue", width=2)
        elif self.state=="i":
            # We currently choose a running id
            self.propRunId = self.curRunId+(event.y-self.oldY)/20	    	    	    
            if self.propRunId<0:
                self.propRunId=0
            if self.propRunId>MAX_RUNID:
                self.propRunId=MAX_RUNID		
            self.canvas.create_rectangle(self.curx1,self.cury1,self.curx1+30,
            self.cury1+30, outline="white", fill="white")
            self.canvas.create_text(self.curx1+15,self.cury1+15, text=str(self.propRunId),
            fill="blue", font=("Helvectica", "20"))	
        elif self.state=="ul":
            # We currently move the upper left corner
            self.curx1=min(maxx,max(1,event.x))
            self.cury1=min(maxy,max(1,event.y))
            self.canvas.create_rectangle(self.curx1, self.cury1, self.curx2, self.cury2,
            outline="blue", width=2)
            #ELtodo self.drawAnchorPoint(self.curx1, self.cury1)
        elif self.state=="ur":
            # We currently move the upper right corner
            self.curx2=min(maxx,max(1,event.x))
            self.cury1=min(maxy,max(1,event.y))
            self.canvas.create_rectangle(self.curx1, self.cury1, self.curx2, self.cury2,
            outline="blue", width=2)
            #ELtodo self.drawAnchorPoint(self.curx2, self.cury1)
        # We currently move the lower left corner
        elif self.state=="ll":
            self.curx1=min(maxx,max(1,event.x))
            self.cury2=min(maxy,max(1,event.y))
            self.canvas.create_rectangle(self.curx1, self.cury1, self.curx2, self.cury2,
            outline="blue", width=2)
            #ELtodo self.drawAnchorPoint(self.curx1, self.cury2)
        elif self.state=="lr":
            # We currently move the lower right corner
            self.curx2=min(maxx,max(1,event.x))
            self.cury2=min(maxy,max(1,event.y))
            self.canvas.create_rectangle(self.curx1, self.cury1, self.curx2, self.cury2,
            outline="blue", width=2)
            #ELtodo self.drawAnchorPoint(self.curx2, self.cury2)
        elif self.state=="c":
            # We currently move the whole rectangle
            self.curx1=min(maxx-10,max(1,event.x-int(0.5*self.curwidth)))
            self.cury1=min(maxy-10,max(1,event.y-int(0.5*self.curheigth)))
            self.curx2=min(maxx,max(self.curx1+10,max(1,event.x+int(0.5*self.curwidth))))
            self.cury2=min(maxy,max(self.cury1+10,max(1,event.y+int(0.5*self.curheigth))))

            self.canvas.create_rectangle(self.curx1, self.cury1, self.curx2, self.cury2,
            outline="blue", width=2)
            #ELtodo self.drawAnchorPoint(event.x, event.y)
            # Drag outside of the canvas -> delete
            #if (event.x<0) or (event.x>self.img.size[0]) or (event.y<0) or (event.y>self.img.size[1]):
            #    self.canvas.create_image(self.curx1, self.cury1, anchor=NW, image=self.imgTrash)
            #    self.canvas.create_image(self.curx1, self.cury2-40, anchor=NW, image=self.imgTrash)
            #    self.canvas.create_image(self.curx2-40, self.cury1, anchor=NW, image=self.imgTrash)
            #    self.canvas.create_image(self.curx2-40, self.cury2-40, anchor=NW, image=self.imgTrash)		
    def saveXML(self,event):
        self.ct.videoname=self.fnEntry.get()
        self.ct.exportXML()
        self.checkValidity()
        self.isModified=False        
        
    # Remove all rectangles of the current frame
    def deleteAllRects(self,event):
        self.ct.deleteAllRects()
        self.displayAnno() 
        self.canvas.update()
        self.isModified=True
        
    # Remove the currently selected rectangle of the current frame
    def deleteCurRect(self,event):
        sempos = self.ct.getSemMousePos(self.mousex,self.mousey)
        if sempos.index > -1:
            self.ct.deleteRect(sempos.index)
            self.displayAnno() 
            self.canvas.update()
        self.isModified=True            
            
    def leftMouseDown(self,event):
        #self.debugEvent('leftMouseDown')
    
        # On a Mac the right click does not work, at least not expected
        # workaround: if the CTRL key is held with a left click, we consider
        # it a right click
        if (event.state & 0x0004) > 0:
            self.rightMouseDown(event)
            return
    
        # Which rectangle is the nearest one to the mouse cursor, and what is
        # its relative position (corners, center, general position)?
        sempos = self.ct.getSemMousePos(self.mousex,self.mousey)
        
        # We change an existing rectangle. Remove the old one from the 
        # controler
        if sempos.sempos in ("ul","ur","ll","lr","c"):
            self.state=sempos.sempos
            r=self.ct.getRects()[sempos.index]
            self.curx1=r.x1
            self.cury1=r.y1
            self.curx2=r.x2
            self.cury2=r.y2
            self.curwidth=abs(r.x2-r.x1)
            self.curheigth=abs(r.y2-r.y1)
            self.curRunId=r.runid
            self.ct.delRect(sempos.index)	    
            
        # We start drawing a new rectangle
        else:
            self.state="d"
            self.curRunId=self.runIdProposed4NewRect            
            self.curx1=event.x
            self.cury1=event.y
            self.curx2=-1
            self.cury2=-1
            
        self.curSempos = SemMousePos(-1,"g")
            
    def leftMouseUp(self,event):
        #self.debugEvent('leftMouseUp')
    
        # On a Mac the right click does not work, at least not expected
        # workaround: if the CTRL key is held with a left click, we consider
        # it a right click
        if (event.state & 0x0004) > 0:
            self.rightMouseUp(event)
            return
        
        if self.state in ("ul","ur","ll","lr","c","d"):	    	    
            # Are we inside the window?
            if True: #not ((event.x<0) or (event.x>self.img.size[0]) or (event.y<0) or (event.y>self.img.size[1])):		
                
                # If we create a new rectangle, we check whether we moved 
                # since the first click (Non trivial rectangle)? 
                if (self.state!="d") or (abs(event.x-self.curx1)>5) or (abs(event.y-self.cury1)>5):

                    self.ct.addRect(self.curx1,self.cury1,self.curx2,self.cury2,self.curRunId);  
                    self.isModified=True
                    # We just drew a new rectangle
                    if self.state=="d":
                        self.ct.useRunId(self.curRunId)
                        self.displayRunIds()  
                        self.runIdProposed4NewRect = self.runIdProposed4NewRect+1
            self.curx2=event.x
            self.cury2=event.y	
        self.state=""
        self.displayAnno()

    def rightMouseDown(self,event):
        print "right mouse down"
        sempos=self.ct.getSemMousePos(event.x,event.y)
        self.curSempos = sempos
        self.oldY=event.y
        print "sempos.index",sempos.index
        if sempos.index>=0:
            self.state="i"      
            r=self.ct.getRects()[sempos.index]
            self.curRunId=r.runid
            self.curx1=r.x1
            self.cury1=r.y1                

    def rightMouseUp(self,event):	
        if self.state=="i":	    
            self.ct.updateRunId(self.curSempos.index,self.propRunId)            
            self.displayRunIds()
            self.isModified=True
        self.state=""
        
    def choseRunId(self,event,id):
        sempos=self.ct.getSemMousePos(self.mousex,self.mousey)
        print "choseRunId(3):",sempos.index, "pos: ",self.mousex,",",self.mousey
        if sempos.index>-1:
            self.ct.updateRunId(sempos.index,id)            
            self.displayAnno()         
            self.displayRunIds() 
            self.isModified=True
        
#ENDCUT

    # draw an anchor point at (x, y) coordinates
    def drawAnchorPoint(self, draw, x, y, size=5, color="cyan"):
        x1 = x-size
        y1 = y-size
        x2 = x+size
        y2 = y+size
        draw.ellipse([x1, y1, x2, y2], outline=color)
        draw.ellipse([x1+1, y1+1, x2-1, y2-1], outline=color)
        draw.ellipse([x1+2, y1+2, x2-2, y2-2], outline=color)


    # Draw the image and the current annotation
    def displayAnno(self):
        if self.state in ("ul","ur","ll","lr","c","d","i"):
            # We are currently in an operation, so do not search 
            # the nearest rectangle. It is the one blocked at the
            # beginning of the operation
            sempos = self.curSempos
        else:	
            # Search for the nearest rectangle:
            # which rectangle is the nearest one to the mouse cursor, 
            # and what is its relative position (corners, center,
            # general position)?
            sempos = self.ct.getSemMousePos(self.mousex,self.mousey)	
       
        # Init drawing
        drawFrame = self.img.copy()
        draw = ImageDraw.Draw(drawFrame)

        # Draw all rectangles
        for (i,r) in enumerate(self.ct.getRects()):
            if i == sempos.index:
                curcol = "blue"
            else:
                curcol = "red"    
            draw.rectangle([r.x1, r.y1, r.x2, r.y2], outline=curcol)	    
            draw.rectangle([r.x1+1, r.y1+1, r.x2-1, r.y2-1], outline=curcol)
            draw.text([r.x1+3, r.y1+2], str(r.runid), font=self.imgFont, fill=curcol)

#BEGCUT            
            # Draw the icons 
            if i == sempos.index:
                if sempos.sempos == "ul":
                    self.drawAnchorPoint(draw, r.x1, r.y1)
                if sempos.sempos == "ur":
                    self.drawAnchorPoint(draw, r.x2, r.y1)
                if sempos.sempos == "ll":
                    self.drawAnchorPoint(draw, r.x1, r.y2)
                if sempos.sempos == "lr":
                    self.drawAnchorPoint(draw, r.x2, r.y2)
                if sempos.sempos == "c":
                    cx=0.5*(r.x1+r.x2)
                    cy=0.5*(r.y1+r.y2)
                    self.drawAnchorPoint(draw, cx, cy)
#ENDCUT
        del draw
        self.drawPhoto = ImageTk.PhotoImage(drawFrame)
        self.canvas.create_image(0, 0, anchor=NW, image=self.drawPhoto)	

    def displayRunIds(self):
        self.runidbox.delete(0, END) 
        x=self.ct.runids
        for i in range(len(x)):
            if x[i]<0:
                self.runidbox.insert(END, str(i+1)+" has no assigned class ")
            else:
                self.runidbox.insert(END, str(i+1)+" has class "+str(x[i])+" ["+classnames[x[i]-1]+"]")
               
#BEGCUT               
    # a listbox item has been clicked: choose the object class for 
    # a given object
    def runidboxClick(self,event):                            
        self.clickedRunId = self.runidbox.curselection()
        top = self.classDlg = Toplevel()
        top.geometry("400x400+"+str(self.winfo_rootx())+"+"+str(self.winfo_rooty()))
        top.title("Enter class label for chosen object")
        classId = 0
        for classname in classnames:
            classId += 1
            buttonText = str(classId) + " " + classname
            button = Button(top, text=buttonText, command= lambda i=classId: self.choseClassNr(i))
            button.pack(fill=X)
                
    def choseClassNr(self,classNr):
        runid=int(self.clickedRunId[0])        
        self.ct.runids[runid]=classNr
        self.classDlg.destroy()
        self.displayRunIds()
        # Put the focus on the canvas, else the listbox gets all events        
        self.canvas.focus_force()
        self.isModified=True
        
    def choseRunId1(self,event):
        self.choseRunId(event,1)
    def choseRunId2(self,event):
        self.choseRunId(event,2)
    def choseRunId3(self,event):
        self.choseRunId(event,3)
    def choseRunId4(self,event):
        self.choseRunId(event,4)
    def choseRunId5(self,event):
        self.choseRunId(event,5)
    def choseRunId6(self,event):
        self.choseRunId(event,6)
    def choseRunId7(self,event):
        self.choseRunId(event,7)
    def choseRunId8(self,event):
        self.choseRunId(event,8)
    def choseRunId9(self,event):
        self.choseRunId(event,9)
    def choseRunId10(self,event):
        self.choseRunId(event,10)
#ENDCUT

    def debugEvent(self, title):
        self.eventcounter += 1
        print 'event #' + str(self.eventcounter), title


def onexit():
    print "qqqq"
    ex.quit(None)
        
        
trackingLib = None
    

def main():
    curPath=sys.path[0]
#BEGCUT
    global trackingLib
    print "Script installed at: ",curPath        
    
    # load C++ JM tracking library
    if os.name == 'posix':
        # ---- Mac Os
        if platform.system() == 'Darwin':
            trackingLib = ctypes.CDLL(curPath+"/boxtracking/libboxtracking.dylib")
    
        # ---- Linux
        else:
            trackingLib = ctypes.CDLL(curPath+"/boxtracking/libboxtracking.so")

    # ---- Windows
    elif os.name == 'nt':
        trackingLib = ctypes.CDLL(curPath+"/boxtracking/libboxtracking.dll")
    
    
    if trackingLib != None:
        print "JM tracking library loaded." 
        trackingLib.init_lib()
    else:
        print "Failed to load JM tracking library."
    print trackingLib
#ENDCUT

    root = Tk()
    root.protocol("WM_DELETE_WINDOW", onexit) 
    global ex 
    ex = Example(root, curPath)
    root.mainloop()  

if __name__ == '__main__':
    main()  
