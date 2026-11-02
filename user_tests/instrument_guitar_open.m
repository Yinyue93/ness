% guitar instrument: six open strings in standard tuning (E2 A2 D3 G3 B3 E4)

SR = 48000;

% Light acoustic set (.012-.053), 0.65 m scale, standard tuning E2 A2 D3 G3 B3 E4.
% Passing tensions (8th argument) makes string_def_gen produce realistic
% strings: it solves for an effective radius and density from the tension
% and inharmonicity.
material_tab = [7850 2e11];                                 % 1: steel

notes = [-20 -15 -10 -5 -1 4]';                             % semitones from middle C
material = [1 1 1 1 1 1]';
inharmonicity = [2.66e-4 9.52e-5 3.02e-5 9.62e-6 6.07e-5 1.90e-5]';
L = 0.65;                                                   % scale length (m)
T60_0 = [15 14 13 12 10 9]';                                % T60 at DC
T60_1000 = [6 6 5.5 5 5 5]';                                % T60 at 1 kHz
tension = [116 128 136 135 103 104]';                       % N

string_def = string_def_gen(material_tab, notes, material, inharmonicity, L, T60_0, T60_1000, tension);

string_num = 6;

% pickups near the bridge, slightly staggered so the strings don't share
% identical harmonic notches
out_num = 6;
output_def = [1 0.90; 2 0.91; 3 0.89; 4 0.92; 5 0.90; 6 0.91];
normalize_outs = 0;                                         % keep natural string balance

% low strings slightly left, high strings slightly right
pan = [-0.5 -0.3 -0.1 0.1 0.3 0.5];

backboard = [-0.002 -0.001 -0.0002];
frets = fret_def_gen(20, 1, -0.001);
barrier_params_def = [1e10 1.3 10 20 1e-12];
finger_params = [0.005 1e7 3.3 100];
