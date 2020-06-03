# Voice prompts 

This repository contains the voice prompt data and scripts and synthesised voice files, used by the OpenGD77 firmware
https://github.com/rogerclarkmelbourne/OpenGD77

This is a work in progress.

The most stable versions are the UK and USA english versions.

The python script is used to create the voice data pack (.bin) files which are used by the OpenGD77 firmware.

The scripy reads a wordlist file and downloads synthesised audio from various online TextToSpeech sites, which use Amazon Polly as their engine
The speach audio files are downloaded in .ogg format, at 8kHz sample rate.
The files must be in this format, because the audio data rate used by the proprietary codec in the OpenGD77 firmware only supports 8kHz sample rate
Ogg format is used becuase MP3 files seem to have some silence at the beginning which can't be removed, which affects the final playback of the audio by the firmware

One the speech files have been downloaded, they are converted to AMBE format using the proprietary codec running in the OpenGD77 firmware.
The python script sends blocks of 80 samples to the firmware via USB Serial, and the firmware encodes these samples into 27 bytes of AMBE data, which is read back by the script
Ogg data can't be sent directly to the firmware, as it only supports RAW 16 bit signed LittleEndian format samples, so the OGG files are converted to RAW using FFPMEG

One a file has been encoded to AMBE, it is saved as a .amb file

Once all files have been processed to AMBE, the script packages the files into a single Voice Prompt pack, binary file.

This file can then be uploaded to the OpenGD77 firmare for later playback, using the OpenGD77 CPS
https://github.com/rogerclarkmelbourne/OpenGD77CPS
