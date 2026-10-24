"""Original SVG teaching maps; deliberately not replicas of vendor interfaces."""
from pathlib import Path
from html import escape
import json

ROOT = Path(__file__).resolve().parents[1]
MAPS = {
    'reverb': ('Pro-R 2', [
        ('predelay', 'Predelay', '预延迟', 9, 48), ('space', 'Space', '空间 / 尾音时间', 36, 48),
        ('decay', 'Decay Rate', '尾音比例', 51, 48), ('brightness', 'Brightness', '尾音明暗', 66, 48),
        ('ducking', 'Ducking', '唱时降低混响', 80, 48), ('mix', 'Mix', '干湿比例', 93, 48)]),
    'delay': ('Timeless 3', [
        ('time', 'Delay', '重复间隔', 12, 48), ('sync', 'Delay Sync', '节拍同步', 31, 48),
        ('feedback', 'Feedback', '重复衰减', 51, 48), ('wet', 'Wet Level', '湿声电平', 72, 48),
        ('mix', 'Mix', '干湿比例', 91, 48)]),
    'eq': ('Pro-Q 3', [
        ('shape', 'Shape', '滤波形状', 14, 48), ('freq', 'Freq', '处理频率', 38, 48),
        ('gain', 'Gain', '增强 / 削减', 62, 48), ('q', 'Q', '范围宽窄', 86, 48)]),
    'comp': ('Pro-C 2', [
        ('threshold', 'Threshold', '触发阈值', 14, 48), ('ratio', 'Ratio', '压缩比例', 38, 48),
        ('attack', 'Attack', '开始速度', 62, 48), ('release', 'Release', '恢复速度', 86, 48)]),
    'deess': ('Pro-DS', [
        ('threshold', 'Threshold', '齿音阈值', 14, 48), ('range', 'Range', '削减幅度', 38, 48),
        ('mode', 'Single Vocal', '检测模式', 62, 48), ('audition', 'Audition', '检测试听', 86, 48)]),
}


def main():
    out = ROOT / 'app/static/mix-guide/diagrams'
    out.mkdir(exist_ok=True)
    positions = {}
    for key, (name, controls) in MAPS.items():
        elements = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="250" viewBox="0 0 960 250" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(name)} 常用控件教学示意</title>',
            '<desc id="desc">原创参数卡片，非插件截图；按英文名称在实际插件中定位。</desc>',
            '<rect width="960" height="250" rx="18" fill="#f7f5fc"/>',
            '<g font-family="Segoe UI,Microsoft YaHei,sans-serif">',
            f'<text x="28" y="31" font-size="16" fill="#625177" font-weight="650">{escape(name)} · 常用控件</text>',
            '<text x="930" y="31" text-anchor="end" font-size="12" fill="#9483a5">教学示意 · 非插件截图</text>']
        positions[key] = {}
        for ident, label, chinese, x, y in controls:
            cx, cy = x * 9.6, y * 2.5
            positions[key][ident] = [x, y]
            # Visible dial glyph plus English labels remain sharp at any scale.
            elements.extend([
                f'<circle cx="{cx}" cy="{cy}" r="33" fill="white" stroke="#d5c7e8" stroke-width="3"/>',
                f'<path d="M{cx-25} {cy+20} A32 32 0 1 1 {cx+25} {cy+20}" stroke="#9d81c6" stroke-width="3" fill="none" stroke-linecap="round"/>',
                f'<text x="{cx}" y="{cy+61}" text-anchor="middle" font-size="20" fill="#5a426f" font-weight="600">{escape(label)}</text>',
                f'<text x="{cx}" y="{cy+84}" text-anchor="middle" font-size="16" fill="#8b789d">{escape(chinese)}</text>',
            ])
        elements.append('</g></svg>')
        (out / f'{key}.svg').write_text('\n'.join(elements), encoding='utf-8', newline='\n')
    (out / 'positions.json').write_text(json.dumps(positions, indent=2), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
