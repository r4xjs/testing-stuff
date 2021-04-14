#!/usr/bin/env python3

from os import path, walk
from subprocess import check_call, check_output
import re
import os
import shutil
import time
import traceback


ROOT = path.abspath(".")
REGEN = False


# helper functions

def file_ext(fn):
    return fn.split('.')[-1].lower()

def get_cue_flac(filenames):
    #{{{1
    found_cues = []
    found_cue_flac = []
    
    for filename in filenames:
        if file_ext(filename) == 'cue':
            found_cues.append(filename)
    for cue in found_cues:
        flac = '.'.join(cue.split('.')[:-1]) + '.flac'
        if flac in filenames:
            found_cue_flac.append((cue, flac))
    return found_cue_flac
    #1}}}

def translate_to_mp3_path(filename):
    #{{{1
    # In ROOT should be a flac an mp3 file
    #ls -lh
    #total 8,0K
    #drwxrwxr-x 4 user user 4,0K Mai  1 19:36 flac
    #drwxrwxr-x 2 user user 4,0K Mai  1 19:36 mp3
    if file_ext(filename) != 'flac':
        print("[!] Not a flac file")
        return None
    if not(path.exists(path.join(ROOT, 'mp3')) and \
            path.exists(path.join(ROOT, 'flac'))
            ):
        print("[!] ROOT dir doesn't have flac and or mp3 directory")
        return None
    # ROOT/flac/balll/foo.flac => ROOT/mp3/balll/ff_foo.mp3
    tmp = path.join(ROOT, 'mp3', '/'.join(filename.replace(ROOT, '').split('/')[2:]))
    if not path.basename(tmp).startswith('ff_'):
        tmp = path.join(path.dirname(tmp), 'ff_' + path.basename(tmp))
    return '.'.join(tmp.split('.')[:-1]) + '.mp3'
    #1}}}

def transcode_flac2mp3(flac, mp3):
    #{{{1
    if not path.basename(mp3).startswith('ff_'):
        mp3 = path.join(path.dirname(mp3), 'ff_'+path.basename(mp3))
    check_call(['ffmpeg', '-y', '-i', flac, '-qscale:a', '0', mp3])
    #1}}}

def get_sr_and_bd(flac):
    #{{{1
    out = check_output(['mediainfo', flac]).decode()
    ret = dict()
    for line in out.split('\n'):
        m = re.search(r'Sampling rate\s+:\s+([\d\.]+)\s+kHz', line)
        if m:
            ret['sr'] = m.group(1)
            continue
        m = re.search(r'Bit depth\s+:\s+(\d+)+\s+bits', line)
        if m:
            ret['bd'] = m.group(1)
            continue
    return ret
    #1}}}

def split_flac(flac, cue):
    #{{{1
    # Note: this function sucks hard, improve this shit
    try:
        old_path = path.abspath(os.curdir)
        os.chdir(path.dirname(flac))
        # if you change the format, make sure you also change it in handle_cule_flacs
        flac_param = get_sr_and_bd(flac)
        if flac_param['bd'] == '16':
            check_call(['shnsplit', '-o', 'flac', '-t', 'ff_%n-%a-%t', '-f', cue, flac])
        elif flac_param['bd'] == '24':
            # TODO: arbitrary code execution vulnerability.... don't care for now
            cmd = "cuebreakpoints \"%s\" | sed 's/$/0/' | shnsplit -o flac \"%s\""%(\
                    cue, flac)
            check_call(cmd, shell=True)
            # after this we have split-track01.flac, split-track02.flac,...
            # rename them to the correct format
            cue_infos = parse_cue_file(cue)
            for track_num in cue_infos.get('tracks', []):
                new_name = "ff_%s-%s-%s.flac"%(track_num, \
                        cue_infos['album'], cue_infos['tracks'][track_num]['title'])
                shutil.move("split-track%s.flac"%(track_num), new_name)
        else:
            print("[!] unkonwn flac param values bd: %s, sr: %s"%(flac_param['bd'],\
                    flac_param['sr']))
        os.chdir(old_path)
    except:
        print("[!] Error during splitting")
        return False
    return True
    #1}}}

def parse_cue_file(cue):
    #{{{1
    # super dirty parsing
    cue_dict = dict()
    current_track = None
    with open(cue, 'r', encoding='latin-1') as fd:
        for line in fd:
            m = re.search(r'title\s+"(.*)"', line, re.IGNORECASE)
            if m and not cue_dict.get('file', False):
                cue_dict['album'] = m.group(1).rstrip('.').replace('/', '-')
                continue

            m = re.search(r'file\s+"(.*)"', line, re.IGNORECASE)
            if m:
                cue_dict['file'] = m.group(1).rstrip('.').replace('/', '-')
                continue

            m = re.search(r'track\s+(\d+)', line, re.IGNORECASE)
            if m:
                current_track = m.group(1)
                if not cue_dict.get('tracks', False):
                    cue_dict['tracks'] = dict()
                cue_dict['tracks'][m.group(1)] = dict()
                
                continue

            m = re.search(r'title\s+"(.*)"', line, re.IGNORECASE)
            if m and current_track is not None:
                cue_dict['tracks'][current_track]['title'] = m.group(1).rstrip('.').replace('/', '-')
                continue

    return cue_dict
    #1}}}

def handle_cue_flacs(flac, cue):
    #{{{1
    # shnsplit -o flac -t "%n-%a-%t" -f Linkin_Park_-_Hybrid_Theory.cue Linkin_Park_-_Hybrid_Theory.flac
    # {'album': 'Hybrid Theory', 'file': 'Linkin Park - Hybrid Theory.flac', 'tracks': {'01': {'title': 'Papercut'}, '02': {'title': 'One Step Closer'}, '03': {'title': 'With You'}, '04': {'title': 'Points Of Authority'}, '05': {'title': 'Crawling'}, '06': {'title': 'Runaway'}, '07': {'title': 'By Myself'}, '08': {'title': 'In The End'}, '09': {'title': 'A Place For My Head'}, '10': {'title': 'Forgotten'}, '11': {'title': 'Cure For The Itch'}, '12': {'title': 'Pushing Me Away'}
    print("HANDLE cue,flac: %s, %s"%(flac, cue))
    cue_infos = parse_cue_file(cue)
    split_and_transcode = False
    mp3s = []
    flacs = []
    for track_num in cue_infos.get('tracks', []):
        # if you cange the format, make sure you also change it in split_flac
        split_file = "ff_%s-%s-%s.flac"%(track_num,  \
            cue_infos.get('album', ''), \
            cue_infos['tracks'][track_num]['title'])
        _flac = path.join(path.dirname(flac), split_file)
        _mp3 = translate_to_mp3_path(_flac.replace(' ', '_'))
        flacs.append(_flac)
        mp3s.append(_mp3)
        if not path.exists(_mp3):
            split_and_transcode = True
            
    if not split_and_transcode and not REGEN:
        print("[+] Already transcoded, skipping %s", flac)
        return
    # this should hopfully generate all files from the `flacs` list
    if not split_flac(flac, cue):
        return False

    # create the folder(s)
    check_call(['mkdir', '-p', path.dirname(mp3s[0])])

    # transcode flac file to mp3
    for idx in range(0, len(flacs)):
        transcode_flac2mp3(flacs[idx], mp3s[idx])

    # remove splitted flac files
    for _flac in flacs:
        os.remove(_flac)

    # add tags
    check_call(['cuetag', cue] + mp3s)

    #1}}}

def handle_single_flac(filename):
    #{{{1
    print("HANDLE single flac file: %s"%(filename))
    mp3_path = translate_to_mp3_path(filename)
    if path.exists(mp3_path) and not REGEN:
        print("[+] Already transcoded, skipping %s", filename)
        return
    # mp3 file/folder doesn't exists yet
    
    # create the folder(s)
    check_call(['mkdir', '-p', path.dirname(mp3_path)])

    # transcode flac file to mp3
    transcode_flac2mp3(filename, mp3_path)
    #1}}}

############################################

def dir_walker():
    #{{{1
    for dirpath, dirname, filenames in walk(path.join(ROOT, 'flac')):
        try:
            abs_files = list(map(lambda x: path.join(dirpath,x), filenames))

            # remove all old ff_ files
            for abs_file in abs_files:
                if path.basename(abs_file).startswith('ff_'):
                    os.remove(abs_file)
            tmp = [x for x in abs_files if not path.basename(x).startswith('ff_')]
            abs_files = tmp

            # first look for flac files with matching cue files
            # split the flac according to the cue file and then transcode the splitted flacs
            cue_flacs = get_cue_flac(abs_files)
            flac_with_cues = [x for _,x in cue_flacs]
            for cue, flac in cue_flacs:
                handle_cue_flacs(flac, cue)

            # all other flac files (without a matching cue file) will be transcoded directly
            for filename in abs_files:
                if file_ext(filename) == 'flac' and filename not in flac_with_cues:
                    handle_single_flac(filename) 
        except:
            print("[!] Error during dir_walker loop.... continue")
            traceback.print_stack()
            time.sleep(3)


    #1}}}


dir_walker()

