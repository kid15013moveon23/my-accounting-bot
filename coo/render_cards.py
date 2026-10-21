"""Render source-grounded COO highlight cards for inline Telegram photos."""
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
PAD = 60


def render_cards(payload, output_dir, font_path=None):
    font_path = font_path or os.environ.get('COO_FONT_PATH', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    fonts = {size: ImageFont.truetype(font_path, size) for size in (26, 30, 34, 38, 44, 54)}
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    cards = payload['cards']
    if not 1 <= len(cards) <= 10:
        raise ValueError('Use one to ten readable highlight cards')
    for index, card in enumerate(cards):
        canvas = Image.new('RGB', (WIDTH, 6000), '#F1F4F8')
        draw = ImageDraw.Draw(canvas)
        y = 0
        def wrap(text, size, limit):
            lines, line = [], ''
            for char in str(text):
                if char == '\n':
                    lines.append(line)
                    line = ''
                elif draw.textlength(line + char, font=fonts[size]) > limit:
                    lines.append(line)
                    line = char
                else:
                    line += char
            if line:
                lines.append(line)
            return lines
        def text(value, size=34, color='#283A50', x=PAD, gap=14):
            nonlocal y
            for line in wrap(value, size, WIDTH-PAD-x):
                draw.text((x,y),line,font=fonts[size],fill=color)
                y += size + gap
        draw.rectangle((0,0,WIDTH,240),fill='#102C48')
        y=40
        text(card['title'],54,'#FFFFFF')
        text(payload['date']+'  |  '+str(index+1)+' / '+str(len(cards)),30,'#BED4E8')
        y=265
        text(payload['notice'],30,'#9A5B10')
        y += 18
        if card.get('table'):
            rows=card['table']
            draw.rounded_rectangle((PAD-20,y-12,WIDTH-PAD+20,y+len(rows)*78+12),radius=20,fill='white')
            for rowindex,row in enumerate(rows):
                if len(row)!=3:
                    raise ValueError('Cards use three-column mobile tables')
                color='#60758A' if rowindex==0 else '#172F48'
                if rowindex:
                    draw.line((PAD,y-8,WIDTH-PAD,y-8),fill='#E8EEF4',width=2)
                for x,value in zip((PAD,310,775),row):
                    draw.text((x,y),str(value),font=fonts[34],fill=color)
                y+=78
            y+=38
        for section in card.get('sections',[]):
            text(section['heading'],38,'#126F78')
            y+=6
            for item in section['items']:
                text('• '+item,34)
                y+=12
            y+=20
        text(card.get('footer','来源：Teams｜缺失数据不推算'),26,'#687C90')
        y+=35
        if y>2400:
            raise ValueError('Card too long for Telegram reading; split highlights')
        path=out / ('coo-card-'+str(index+1)+'.jpg')
        canvas.crop((0,0,WIDTH,y)).save(path,quality=95,subsampling=0)
        paths.append(path)
    return paths


if __name__=='__main__':
    import sys
    render_cards(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')),sys.argv[2])
