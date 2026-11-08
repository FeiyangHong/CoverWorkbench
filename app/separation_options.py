"""Validated inference choices shared by settings, jobs and workers."""
BATCH_SIZES=(1,2,4,8,16)
SONG_MODELS=('big7','deux','hyperace-voc','hyperace-inst','leap-voc','leap-inst')
HARMONY_MODELS=('mel-karaoke','bs-frazer','bs-anvuew')

def batch_size(value):
    if type(value) is not int or value not in BATCH_SIZES:
        raise ValueError('Batch size 请选择 1、2、4、8 或 16')
    return value

def tta(value):
    if type(value) is not bool:raise ValueError('TTA 必须为开启或关闭')
    return value

def defaults(values):
    return {'songModel':values.get('separationSongModel','deux'),
            'harmonyModel':values.get('separationHarmonyModel','bs-frazer'),
            'quality':values.get('separationQuality','high'),
            'batchSize':batch_size(int(values.get('separationBatchSize','4'))),
            'tta':values.get('separationTta','off')=='on'}
