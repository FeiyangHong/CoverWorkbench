"""Render the bilingual README workflow illustrations without external dependencies."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COPY = {
    'zh': {
        'title': '从素材，到作品。',
        'subtitle': '在熟悉的软件里创作，让工作台接手重复步骤。',
        'legend': ['创作软件', '工作台'],
        'footer': '已有调好的 SVP？从第 03 步开始。',
        'steps': [
            ('EXTERNAL TOOLS', '准备干净的人声', ['使用自己的分离工具，', '得到主声、和声与伴奏。'],
             '素材准备', ['确认歌曲版本', '优先使用干净的主声'], 'neutral'),
            ('SYNTHESIZER V', '校对、调声，保存 SVP', ['提取音符，修正歌词与音准，', '完成声库选择和演唱表情。'],
             '工作台在旁辅助', ['歌词与读音准备', '整段填词 · 乐句复用'], 'purple'),
            ('COVERWORKBENCH', '搭好 Studio One 工程', ['读取已保存的 SVP，分配声部，', '按所选模板生成独立 Song。'],
             '初始模板 / 自有模板', ['沿用效果器与路由', '多条主声 / 可无和声'], 'mint'),
            ('STUDIO ONE', '试听、混音，渲染音频', ['调整人声与伴奏的平衡，', '确认效果器，再导出混音。'],
             '保留创作判断', ['新歌仍需试听与微调', '软件与插件由你提供'], 'purple'),
            ('COVERWORKBENCH', '检查音频，整理交付', ['检查响度与峰值，整理字幕，', '打包素材或替换视频音轨。'],
             '最后一步，交给耳朵', ['人工检查声音与画面', '确认满意后自行发布'], 'mint'),
        ],
    },
    'en': {
        'title': 'From source to finished cover.',
        'subtitle': 'Create in familiar tools. Let the workbench handle repetition.',
        'legend': ['Creative tools', 'Workbench'],
        'footer': 'Already have a finished SVP? Start at step 03.',
        'steps': [
            ('EXTERNAL TOOLS', 'Prepare clean vocals', ['Separate your source into lead vocals,', 'harmonies and a backing track.'],
             'START WITH YOUR MEDIA', ['Confirm the song version', 'Prefer an isolated lead'], 'neutral'),
            ('SYNTHESIZER V', 'Edit, express, save SVP', ['Extract notes; refine lyrics and pitch.', 'Choose a voice and shape expression.'],
             'WORKBENCH SUPPORT', ['Prepare lyrics and readings', 'Fill lyrics and reuse phrases'], 'purple'),
            ('COVERWORKBENCH', 'Build the mix session', ['Read saved SVP parts and assign roles.', 'Create a Song from the selected template.'],
             'STARTER OR CUSTOM MIX', ['Reuse effects and routing', 'Multiple leads; harmony optional'], 'mint'),
            ('STUDIO ONE', 'Audition, mix, render', ['Balance vocals with the backing track.', 'Check effects and export your mix.'],
             'KEEP CREATIVE CONTROL', ['Listen and adjust for each song', 'Bring your software and plugins'], 'purple'),
            ('COVERWORKBENCH', 'Check and package', ['Check loudness and peaks; collect subs.', 'Package files or replace video audio.'],
             'THE FINAL LISTEN IS YOURS', ['Review sound and picture', 'Publish when you are ready'], 'mint'),
        ],
    },
}


def render(language, copy):
    elements = []

    def add(markup):
        elements.append(markup)

    def text(x, y, content, size=20, color='#625e73', weight=400, spacing=None):
        tracking = f' letter-spacing="{spacing}"' if spacing is not None else ''
        add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}"{tracking}>{escape(content)}</text>')

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="1110" '
        f'viewBox="0 0 960 1110" role="img" aria-labelledby="title desc" xml:lang="{language}">')
    add(f'<title id="title">{escape(copy["title"])}</title>')
    description = ' → '.join(step[1] for step in copy['steps'])
    add(f'<desc id="desc">{escape(description)}</desc>')
    add('<rect width="960" height="1110" rx="28" fill="#f6f5fa"/>')
    add('<g font-family="Segoe UI, Microsoft YaHei, PingFang SC, Arial, sans-serif">')
    text(40, 46, 'THE COVER WORKFLOW', 12, '#8b7aa9', 600, 2)
    text(40, 91, copy['title'], 34, '#30283f', 700)
    text(40, 125, copy['subtitle'], 19)
    palettes = {
        'neutral': ('#eef0f5', '#647087', '#f5f6f9'),
        'purple': ('#eee8ff', '#7556cc', '#f7f4ff'),
        'mint': ('#e0f3eb', '#317a61', '#eff9f4'),
    }
    # Read top-to-bottom; short connectors keep labels full-sized at README width.
    for index, (app, title, lines, aside, details, kind) in enumerate(copy['steps']):
        y = 158 + index * 174
        tint, accent, panel = palettes[kind]
        if index:
            previous_bottom = y - 28
            add(f'<path d="M86 {previous_bottom + 5}v14m-4-4 4 4 4-4" '
                'stroke="#b8adc9" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
        add(f'<rect x="40" y="{y + 3}" width="880" height="146" rx="18" fill="#eae6f0" opacity=".5"/>')
        add(f'<rect x="40" y="{y}" width="880" height="146" rx="18" fill="white" stroke="#e6e1ee"/>')
        add(f'<rect x="64" y="{y + 24}" width="44" height="44" rx="14" fill="{tint}"/>')
        text(73, y + 53, f'{index + 1:02}', 21, accent, 700)
        text(130, y + 30, app, 12, accent, 700, 1.3)
        text(130, y + 64, title, 26, '#332c43', 650)
        for line_index, line in enumerate(lines):
            text(130, y + 98 + line_index * 26, line, 18)
        add(f'<rect x="618" y="{y + 14}" width="288" height="118" rx="12" fill="{panel}"/>')
        text(636, y + 44, aside, 14 if language == 'en' else 17, accent, 600)
        for line_index, line in enumerate(details):
            text(636, y + 76 + line_index * 26, line, 16 if language == 'en' else 18)
    add('<circle cx="48" cy="1040" r="5" fill="#997be3"/>')
    text(63, 1046, copy['legend'][0], 15)
    legend_x = 220 if language == 'en' else 170
    add(f'<circle cx="{legend_x}" cy="1040" r="5" fill="#72b59a"/>')
    text(legend_x + 15, 1046, copy['legend'][1], 15)
    text(40, 1082, copy['footer'], 18, '#766289', 600)
    text(778, 1082, 'CoverWorkbench', 14, '#9b90aa', 600)
    add('</g></svg>')
    return '\n'.join(elements) + '\n'


if __name__ == '__main__':
    for language, copy in COPY.items():
        destination = ROOT / 'docs/images' / f'workflow-{language}.svg'
        destination.write_text(render(language, copy), encoding='utf-8', newline='\n')
        print(destination.name)
