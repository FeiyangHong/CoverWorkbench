"""Opaque picture layers, ordered bottom to top; legacy projects keep one implicit track."""

DEFAULT = 'V1'


def track_of(clip):
    return clip.get('track', DEFAULT)


def tracks(comp):
    return comp.get('tracks') or [{'id': DEFAULT, 'name': '视频 1', 'hidden': False}]


def clips_on(comp, ident):
    return sorted((c for c in comp['clips'] if track_of(c) == ident), key=lambda c: c['start'])


def visible_clips(comp):
    enabled = {t['id'] for t in tracks(comp) if not t.get('hidden')}
    return [c for c in comp['clips'] if track_of(c) in enabled]


def front(comp, frame):
    fps = comp['fps']
    for track in reversed(tracks(comp)):
        if track.get('hidden'): continue
        rows = clips_on(comp, track['id'])
        for i, right in enumerate(rows):
            tr = right.get('transition')
            if not tr or not i: continue
            cut = round(right['start']*fps); half = round(tr['duration']*fps/2)
            if cut-half <= frame < cut+half:
                return {'start': cut-half, 'end': cut+half, 'left': rows[i-1], 'right': right, **tr}, right
        clip = next((c for c in rows if round(c['start']*fps) <= frame < round((c['start']+c['duration'])*fps)), None)
        if clip: return None, clip
    return None, None
