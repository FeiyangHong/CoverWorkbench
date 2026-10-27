"""Windows path-component rules, independent of the execution platform."""
import re

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r'^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$', re.I)


def component(value, label='名称', suffix=''):
    if not isinstance(value, str) or not value.strip() or value in ('.', '..'):
        raise ValueError(label + '不能为空，也不能是 . 或 ..')
    if INVALID.search(value):
        raise ValueError(label + '不能包含 Windows 非法字符 < > : " / \\ | ? * 或控制字符')
    if value.endswith(('.', ' ')):
        raise ValueError(label + '不能以空格或句点结尾')
    if RESERVED.fullmatch(value.split('.')[0].rstrip(' ')):
        raise ValueError(label + '不能使用 Windows 保留名称，例如 CON、NUL、COM1')
    if len((value + suffix).encode('utf-16-le')) // 2 > 255:
        raise ValueError(label + '超过 Windows 单个文件名的 255 个 UTF-16 单元限制（含扩展名或版本后缀）')
    return value


def generated(value, suffix):
    """Leave room for a generated suffix without splitting a Unicode character."""
    while len((value + suffix).encode('utf-16-le')) // 2 > 255:
        value = value[:-1]
    return component(value + suffix)
