import urllib.request
import json
import csv
import os, sys
import time
import os
import subprocess
import struct
import serial
import platform
import getopt, sys
import serial.tools.list_ports
import ntpath
import shutil
import webbrowser


MAX_TRANSFER_SIZE = 32

FLASH_SEND_SIZE = 8
FLASH_WRITE_SIZE = 2

def serialInit(serialDev):
    ser = serial.Serial()
    ser.port = serialDev
    ser.baudrate = 115200
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_ONE
    ser.timeout = 1000.0
    #ser.xonxoff = 0
    #ser.rtscts = 0
    ser.write_timeout = 1000.0
    try:
        ser.open()
    except serial.SerialException as err:
        print(str(err))
        sys.exit(1)
    return ser


def parseFMTChunk(wav_file):
    print("parseFMTChunk")

    audio_format = struct.unpack('<H', wav_file.read(2))[0]
    assert audio_format == 1, '1 == PCM Format: assumed PCM'

    num_channels = struct.unpack('<H', wav_file.read(2))[0]
    print("num_channels = " + str(num_channels))

    sample_rate = struct.unpack('<I', wav_file.read(4))[0]
    print("sample_rate = " + str(sample_rate))

    byte_rate = struct.unpack('<I', wav_file.read(4))[0]
    print("byte_rate = " + str(byte_rate))

    block_align = struct.unpack('<H', wav_file.read(2))[0]
    print("block_align = " + str(block_align))

    bitsPerSample = struct.unpack('<H', wav_file.read(2))[0]
    print("bitsPerSample = " + str(bitsPerSample))    


def convertWAVToRaw(infile,outfile):
    # Open the example wave file stored in the current directory.

    print(infile);
    with open(infile, 'rb') as wav_file:
        # Main Header
        chunk_id = wav_file.read(4)
        assert chunk_id == b'RIFF', 'RIFF little endian, RIFX big endian: assume RIFF'

        chunk_size = struct.unpack('<I', wav_file.read(4))[0]
        #print("Chunk size = " + str(chunk_size));
        
        wav_format = wav_file.read(4)
        assert wav_format == b'WAVE', wav_format

        foundDataChunk = False

        while foundDataChunk==False:
            sub_chunk_id = wav_file.read(4)
            sub_chunk_size = struct.unpack('<I', wav_file.read(4))[0]
#            print("sub_chunk_id = " + str(sub_chunk_id))
#            print("sub_chunk_size = " + str(sub_chunk_size))

            #if (sub_chunk_id == b'fmt '):
            #   parseFMTChunk(wav_file)
            #elif (sub_chunk_id == b'data'):
            if (sub_chunk_id == b'data'):
                foundDataChunk = True
            else:
                wav_file.read(sub_chunk_size)

#        print("Found DATA block")

        print("Saving to "+outfile);
        with open(outfile, 'wb') as raw_file:
            raw_file.write(wav_file.read())
            raw_file.close

        wav_file.close()



# DON'T USE THIS FUNCTION
# ALTHOUGH IT DOES DOWNLOAD THE FILE, there is some problem with the audio format, which causes problems for the AMBE encoder in the radio
def downloadTTSMP3(file_name,promptText):
    myobj = {'msg': promptText,
             'lang':voiceName,
             'source':'ttsmp3.com'}
    data = urllib.parse.urlencode(myobj)
    data = data.encode('ascii')
    print("Download TTSMP3" + file_name + " -> " + promptText)

    with urllib.request.urlopen("https://ttsmp3.com/makemp3_new.php", data) as f:
        resp = f.read().decode('utf-8')
        print(resp)
        data = json.loads(resp)
        if (data['Error'] == 0):
            print(data['URL'])
            # Download the file from `url` and save it locally under `file_name`:
            with urllib.request.urlopen(data['URL']) as response, open(voiceName + "/S44_1k_" +file_name, 'wb') as out_file:
                mp3data = response.read() # a `bytes` object
                out_file.write(mp3data)
                ## need to resample to 8kHz sample rate because ttsmp3 files are 22.05kHz
                out_file.close()
   
                CREATE_NO_WINDOW = 0x08000000
                subprocess.call(['ffmpeg','-y','-i', voiceName + "/S44_1k_" + file_name,'-ar','8000',voiceName + "/" +file_name])#, creationflags=CREATE_NO_WINDOW)

        else:
            print("Error requesting sound")


        




def getMemoryArea(ser,buf,mode,bufStart,radioStart,length):
    R_SIZE = 8
    snd = bytearray(R_SIZE)
    snd[0] = ord('R')
    snd[1] = mode
    bufPos = bufStart
    radioPos = radioStart
    remaining = length
    while (remaining > 0):
        batch = min(remaining,MAX_TRANSFER_SIZE)
        snd[2] = (radioPos >> 24) & 0xFF
        snd[3] = (radioPos >> 16) & 0xFF
        snd[4] = (radioPos >>  8) & 0xFF
        snd[5] = (radioPos >>  0) & 0xFF
        snd[6] = (batch >> 8) & 0xFF
        snd[7] = (batch >> 0) & 0xFF
        ret = ser.write(snd)
        if (ret != R_SIZE):
            print("ERROR: write() wrote " + str(ret) + " bytes")
            return False
        while (ser.in_waiting == 0):
            time.sleep(0)
            
        rcv = ser.read(ser.in_waiting)
        if (rcv[0] == ord('R')):
            gotBytes = (rcv[1] << 8) + rcv[2]
            for i in range(0,gotBytes):
                buf[bufPos] = rcv[i+3]
                bufPos += 1
            radioPos += gotBytes
            remaining -= gotBytes
        else:
            print("read stopped (error at " + str(radioPos) + ")")
            return False
    return True



def sendCommand(ser,commandNumber, x_or_command_option_number, y, iSize, alignment, isInverted, message):
    # snd allocation? len 64 or 32? or 23?
    snd = bytearray(7+16)
    snd[0] = ord('C')
    snd[1] = commandNumber
    snd[2] = x_or_command_option_number
    snd[3] = y
    snd[4] = iSize
    snd[5] = alignment
    snd[6] = isInverted
    # copy message to snd[7] (max 16 bytes)
    i = 7
    for c in message:
        if (i > 7+16-1):
            break
        snd[i] = ord(c)
        i += 1
    ser.flush()
    ret = ser.write(snd)
    if (ret != 7+16): # length?
        print("ERROR: write() wrote " + str(ret) + " bytes")
        return False
    while (ser.in_waiting == 0):
        time.sleep(0)
    rcv = ser.read(ser.in_waiting)
    return len(rcv) > 2 and rcv[1] == snd[1]


def wavSendData(ser,buf,radioStart,length):
    snd = bytearray(FLASH_SEND_SIZE+MAX_TRANSFER_SIZE)
    snd[0] = ord('W')
    snd[1] = 7#data type 7
    bufPos = 0
    radioPos = radioStart
    remaining = length
    while (remaining > 0):
        transferSize = min(remaining,MAX_TRANSFER_SIZE)
        snd[2] = (radioPos >> 24) & 0xFF
        snd[3] = (radioPos >> 16) & 0xFF
        snd[4] = (radioPos >>  8) & 0xFF
        snd[5] = (radioPos >>  0) & 0xFF
        snd[6] = (transferSize >>  8) & 0xFF
        snd[7] = (transferSize >>  0) & 0xFF
        snd[FLASH_SEND_SIZE:FLASH_SEND_SIZE+transferSize] = buf[bufPos:bufPos+transferSize]
        ret = ser.write(snd)
        if (ret != FLASH_SEND_SIZE+transferSize):
            print("ERROR: write() wrote " + str(ret) + " bytes")
            return False
        while (ser.in_waiting == 0):
            time.sleep(0)
        rcv = ser.read(ser.in_waiting)
        if not (rcv[0] == snd[0] and rcv[1] == snd[1]):
            print("ERROR: at "+str(radioPos))
        bufPos += transferSize
        radioPos += transferSize
        remaining -= transferSize
    return True

def convert2AMBE(ser,infile,outfile,stripSilence):
    print("Compress to AMBE "+infile + " -> " + outfile);
    with open(infile,'rb') as f:
        ambBuf = bytearray(16*1024)# arbitary 16k buffer
        buf = bytearray(f.read())
        f.close();
        sendCommand(ser,0, 0, 0, 0, 0, 0, "")#show CPS screen as this disables the radio etc
        sendCommand(ser,6, 5, 0, 0, 0, 0,  "")#codecInitInternalBuffers
        wavBufPos = 0
        print(infile+" " , end='');
        bufLen = len(buf)
        ambBufPos=0;
        ambFrameBuf = bytearray(27)
        startPos=0
        stripSilence=False
        if (stripSilence):
            while (buf[startPos]< 10 and buf[(startPos+1)]==0):
               startPos = startPos + 2;

            print("Startpos "+str(startPos));
               

        while (wavBufPos < bufLen):
            print('.', end='')
            sendCommand(ser,6, 6, 0, 0, 0, 0,  "")#codecInitInternalBuffers
            transferLen = min(960,bufLen-wavBufPos)
            wavSendData(ser,buf[wavBufPos:wavBufPos+transferLen],0,transferLen)
            getMemoryArea(ser,ambFrameBuf,8,0,0,27)# mode 8 is read from AMBE
            ambBuf[ambBufPos:ambBufPos+27] = ambFrameBuf
            wavBufPos = wavBufPos + 960
            ambBufPos = ambBufPos + 27
            
        sendCommand(ser,5, 0, 0, 0, 0, 0, "")# close CPS screen
        with open(outfile,'wb') as f:
            f.write(ambBuf[0:ambBufPos])

        print("")#newline

def convertMP3ToWav(inFile,outFile):
    print("ConvertToWav "+ inFile)
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    subprocess.call(['ffmpeg','-y','-i', inFile,'-acodec','pcm_s16le',outFile], creationflags=CREATE_NO_WINDOW)#,'-filter:a','volume=3dB', '-ar','8000'


def convertToRaw(inFile,outFile):
    print("ConvertToRaw "+ inFile + " -> " + outFile)
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    #'-af','silenceremove=1:0:-50dB'
    subprocess.call(['ffmpeg','-y','-i', inFile,'-f','s16le',outFile], creationflags=CREATE_NO_WINDOW)#,'-filter:a','volume=3dB', '-ar','8000'


def downloadPollyPro(voiceName,file_name,promptText,speechSpeed):
    retval=True
    myobj = {'text-input': promptText,
             'voice':voiceName,
             'format':'ogg_vorbis',# mp3 or ogg_vorbis or json
             'frequency':'8000',
             'effect':speechSpeed}

    data = urllib.parse.urlencode(myobj)
    data = data.encode('ascii')

    with urllib.request.urlopen("https://voicepolly.pro/speech-converter.php", data) as f:
        resp = f.read().decode('utf-8')
        print("Downloading synthesised speech for text: \""+promptText + "\" -> " +file_name)
        if resp.endswith('.ogg'):
            with urllib.request.urlopen(resp) as response, open(voiceName + "/" +file_name, 'wb') as out_file:
                mp3data = response.read() # a `bytes` object
                out_file.write(mp3data)
                retval=True
        else:
            print("Error requesting sound " + resp)  
            retval=False

    return retval
    
def downloadSpeechForWordList(filename,voiceName):
    retval = True
    path = os.path.dirname(sys.argv[0]) 
    with open(filename,"r",encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            promptName = row['PromptName'].strip()
            if (downloadPollyPro(voiceName,"P_{0}".format(promptName)+".ogg",row['PromptText'],row['PromptSpeed'])==False):
                retval=False
                break
    return retval

def encodeWordList(ser,filename,voiceName,forceReEncode):
    path = os.path.dirname(sys.argv[0]) 
    with open(filename,"r",encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            promptName = row['PromptName'].strip()
            fileStub = "P_{0}".format(promptName)

            if  (os.path.exists(path+'/'+voiceName+"/" + fileStub+".amb") == False) or (forceReEncode==True):
                convertToRaw(path +'/'  + voiceName + "/" + fileStub+".ogg",path+'/'+voiceName+"/"+fileStub+".raw")

                stripSilence=True;
                
                if (row['PromptText'] == " "):
                    stripSilence = False
                    
                convert2AMBE(ser,path + '/'+voiceName+"/"+fileStub+".raw",path+'/'+voiceName+"/" + fileStub+".amb",stripSilence)
                os.remove(path + '/'+voiceName+"/"+fileStub+".raw")                    
            
def buildDataPack(filename,voiceName,outputFileName):
    print("Building Data Pack")
    promptsDict={}#create an empty dictionary
    path = os.path.dirname(sys.argv[0]) 
    with open(filename,"r",encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            promptName = row['PromptName'].strip()
            infile = path+'/'+voiceName+"/P_" + promptName+".amb"
            with open(infile,'rb') as f:
                promptsDict[promptName] = bytearray(f.read())
                f.close()

    headerTOCSize = 256*4 + 4 + 4
    outBuf = bytearray(headerTOCSize)
    outBuf[0:3]  = bytes([0x56, 0x50, 0x00, 0x00])#Magic number 
    outBuf[4:7]  = bytes([0x01, 0x00, 0x00, 0x00])#Version number = 1
    outBuf[8:11] = bytes([0x00, 0x00, 0x00, 0x00])#Fist prompt audio is at offset zero
    bufPos=12;
    cumulativelength=0;
    for prompt in promptsDict:
        cumulativelength = cumulativelength + len(promptsDict[prompt]);
        outBuf[bufPos+3] = (cumulativelength >> 24) & 0xFF
        outBuf[bufPos+2] = (cumulativelength >> 16) & 0xFF
        outBuf[bufPos+1] = (cumulativelength >>  8) & 0xFF
        outBuf[bufPos+0] = (cumulativelength >>  0) & 0xFF
        bufPos = bufPos + 4

    #outputFileName = voiceName+'/voice_prompts_'+voiceName+'.bin'
    with open(outputFileName,'wb') as f:
        f.write(outBuf[0:headerTOCSize])#Should be headerTOCSize
        for prompt in promptsDict:
            f.write(promptsDict[prompt])
    f.close()
    print("Created voice pack "+outputFileName);


PROGRAM_VERSION = "0.0.1"

def usage(message):
    print("GD-77 voice prompts creator. v" + PROGRAM_VERSION)
    if (message!=""):
        print()
        print(message)
        print()
        
    print("Usage:  " + ntpath.basename(sys.argv[0]) + " [OPTION]")
    print("")
    print("    -h Display this help text,")
    print("    -f=<worlist_csv_file> : Wordlist file. Required for all functions")
    print("    -n=<Voice_name>       : Voice name for synthesised speech from Voicepolly.pro and temporary folder name")
    print("    -s                    : Download synthesised speech Voicepolly.pro")
    print("    -e                    : Encode previous download synthesised speech files, using the GD-77")
    print("    -b                    : Build voice prompts data pack from Encoded spech files ")
    print("    -d, --device=<device> : Use the specified device as serial port,")
    print("")

def main():
    fileName   = ""#wordlist_english.csv"
    outputName = ""#voiceprompts.bin"
    voiceName = ""#Matthew or Nicole etc
	
    # Default tty
    if (platform.system() == 'Windows'):
            serialDev = "COM71"
    else:
            serialDev = "/dev/ttyACM0"
    #Automatically search for the OpenGD77 device port	
    for port in serial.tools.list_ports.comports():
            if (port.description.find("OpenGD77")==0):
                    #print("Found OpenGD77 on port "+port.device);
                    serialDev = port.device		
	
    # Command line argument parsing
    try:                                
        opts, args = getopt.getopt(sys.argv[1:], "hf:n:seb:d:")
    except getopt.GetoptError as err:
        print(str(err))
        usage("")
        sys.exit(2)

    if (str(shutil.which("ffmpeg.exe")).find("ffmpeg") == -1):
        usage("ERROR: You must install ffmpeg. See https://www.ffmpeg.org/download.html")
        #webbrowser.open("https://www.ffmpeg.org/download.html")
        sys.exit(2)

    for opt, arg in opts:
            if opt in ("-h"):
                    usage()
                    sys.exit(2)
            elif opt in ("-f"):
                    fileName = arg  
            elif opt in ("-n"):
                    voiceName = arg  
    
    if (fileName=="" or voiceName==""):
        usage("ERROR: Filename and Voicename must be specified for all operations")
        sys.exit(2)	
		
    if not os.path.exists(voiceName):
        print("Creating folder " + voiceName + " for temporary files")
        os.mkdir(voiceName);		
	
    for opt, arg in opts:			
        if opt in ("-s"):
            if (downloadSpeechForWordList(fileName,voiceName)==False):
                 sys.exit(2)	
            
    for opt, arg in opts:	
        if opt in ("-d"):
            serialDev = arg		
	
    for opt, arg in opts:			
        if opt in ("-e"):
            ser = serialInit(serialDev)
            encodeWordList(ser,fileName,voiceName,True)
            if (ser.is_open):
                ser.close()
			
    for opt, arg in opts:		
        if opt in ("-b"):
            outputName = arg
            buildDataPack(fileName,voiceName,outputName)



main()
sys.exit(0)
