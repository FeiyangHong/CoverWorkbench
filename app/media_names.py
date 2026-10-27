"""Human-readable media filenames with only Windows-required substitutions."""
from windows_names import INVALID, RESERVED, generated

REPLACEMENTS = dict(zip('<>:"/\\|?*', '＜＞：＂／＼｜？＊'))


def filename(title, extension, version=1):
    if not isinstance(title, str) or not title.strip():
        raise ValueError('下载未返回有效视频标题，请查看下载记录')
    label = INVALID.sub(lambda match: REPLACEMENTS.get(match[0], ' '), title).rstrip(' .') or 'Video'
    if RESERVED.fullmatch(label.split('.')[0].rstrip(' ')):
        label = 'Video - ' + label
    return generated(label, (f'_v{version}' if version > 1 else '') + extension.lower())
