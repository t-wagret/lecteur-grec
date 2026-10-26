"""Nettoyage audio des segments générés : bruit de fond, trous parasites, ratés."""
import librosa
import numpy as np
from scipy.ndimage import uniform_filter
from scipy.signal import butter, sosfiltfilt

N_FFT, HOP = 1024, 256


def debruiter(y, sr, reduction_db=24):
    """Réduction de bruit par seuillage spectral (statistiques minimales par fréquence)."""
    y = sosfiltfilt(butter(4, 70, "hp", fs=sr, output="sos"), y)  # grondements graves
    S = librosa.stft(y, n_fft=N_FFT, hop_length=HOP)
    mag = np.abs(S)
    bruit = np.percentile(mag, 15, axis=1, keepdims=True)
    seuil = bruit * 2.5
    plancher = 10 ** (-reduction_db / 20)
    # gain progressif : plancher sous le seuil, 1 au-dessus de deux fois le seuil
    t = np.clip((mag - seuil) / seuil, 0, 1)
    gain = plancher + (1 - plancher) * t
    gain = uniform_filter(gain, size=(3, 5))  # lisse pour éviter les gazouillis
    return librosa.istft(S * gain, hop_length=HOP, length=len(y))


def adoucir(y, sr, coupure_haute=10000, porte_db=50):
    """Nettoyage léger des segments générés (la voix modèle est déjà propre) :
    coupe les grondements sous 70 Hz et le souffle aigu au-dessus de 10 kHz, puis rend les
    vrais silences parfaitement silencieux, sans toucher au spectre de la parole."""
    y = sosfiltfilt(butter(4, 70, "hp", fs=sr, output="sos"), y)
    y = sosfiltfilt(butter(4, coupure_haute, "lp", fs=sr, output="sos"), y)
    rms = librosa.feature.rms(y=y, frame_length=N_FFT, hop_length=HOP)[0]
    db = 20 * np.log10(rms + 1e-9)
    gain = np.clip((db - (db.max() - porte_db)) / 6, 0, 1)  # fondu de 6 dB sous le seuil
    gain = np.convolve(gain, np.ones(5) / 5, mode="same")
    gain = np.interp(np.arange(len(y)), np.arange(len(gain)) * HOP, gain)
    return y * gain


def compresser_trous(y, sr, max_trou=0.28, top_db=45):
    """Raccourcit les silences internes trop longs et retire ceux des bords.
    Renvoie le signal et la durée du plus long trou interne d'origine (indice de raté)."""
    zones = librosa.effects.split(y, top_db=top_db, frame_length=N_FFT, hop_length=HOP)
    if len(zones) == 0:
        return y[:0], 0.0
    marge = int(0.06 * sr)  # garde les fins de mots douces
    k = int(max_trou * sr / 2)
    fondu = int(0.01 * sr)
    morceaux = [y[max(zones[0][0] - marge, 0): zones[0][1]]]
    plus_long = 0
    for (_, fin_prec), (debut, fin) in zip(zones[:-1], zones[1:]):
        trou = y[fin_prec:debut]
        plus_long = max(plus_long, len(trou))
        if len(trou) > 2 * k:
            a, b = trou[:k].copy(), trou[-k:].copy()
            a[-fondu:] *= np.linspace(1, 0, fondu)
            b[:fondu] *= np.linspace(0, 1, fondu)
            trou = np.concatenate([a, b])
        morceaux += [trou, y[debut:fin]]
    morceaux.append(y[zones[-1][1]: zones[-1][1] + marge])
    sortie = np.concatenate(morceaux)
    return sortie, plus_long / sr


def fondus(y, sr, ms=8):
    """Petits fondus d'entrée et de sortie contre les clics aux raccords."""
    n = min(int(sr * ms / 1000), len(y) // 2)
    if n:
        y = y.copy()
        y[:n] *= np.linspace(0, 1, n)
        y[-n:] *= np.linspace(1, 0, n)
    return y
