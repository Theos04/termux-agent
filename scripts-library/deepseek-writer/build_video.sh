#!/bin/bash
ffmpeg -i hook.mp4 -i build.mp4 -i main_story.mp4 -i climax.mp4 -i ending.mp4 \
       -i music.mp3 -i breathing.wav -i impact.wav \
       -filter_complex "
[0:v]drawtext=text='Most people don'\''t survive meeting the Reaper…':fontcolor=white:fontsize=24:x=10:y=10:enable='between(t,0,3)',colorbalance=rs=0.1:gs=-0.1:bs=-0.1,curves=all='0/0 0.5/0.1 1/1',vignette=angle=PI/3[v0];
[v0][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0[vconcat];
[vconcat]colorbalance=rs=0.15:gs=-0.1:bs=-0.15,curves=all='0/0 0.5/0.1 1/1',vignette=angle=PI/3[vout]
" \
-map "[vout]" -map 5:a -map 6:a -map 7:a \
-c:v libx264 -preset fast -crf 22 -c:a aac -b:a 128k \
-shortest output_video.mp4
