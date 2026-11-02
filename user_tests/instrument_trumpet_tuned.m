%3 valved trumpet, tuned version of examples/instrument_brass.m
%The main tubing (third middle section) is 30 mm longer, like pulling out the
%tuning slide. On the original, the open F4 (3rd resonance) plays about 30 cents
%sharp when the lips are at their best-responding frequency, so an in-tune F4
%needed lips far below the note, which made it start ~1 semitone sharp and take
%over 100 ms to settle. With the slide out, F4 is in tune and settles in ~55 ms;
%higher notes are pulled back up to pitch by the lip frequency, which keeps them fast.
custominstrument=1;%this is 0 if you have a real instrument bore
FS=44100;%sample rate
temperature=20;%temperature in C
vpos=[600,630,660];%position of valve in mm
vdl=[20,20,20];%default (shortest) tube length mm
vbl=[130.7,57.5,199.8];%bypass (longest) tube length mm (will add default length to either side of bypass tubes)
xmeg=10;x0eg=[80,200,575];Leg=1430;
rmeg=20;r0eg=[4,9,3;9,12,1;12,12,1];
rbeg=130;fbeg=6;
