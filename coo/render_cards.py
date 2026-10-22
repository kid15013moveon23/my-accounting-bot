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
        if card.get('chart'):
            chart=card['chart']
            labels=chart['labels']; previous=chart['previous']; current=chart['current']
            if not (len(labels)==len(previous)==len(current)==8):raise ValueError('Eight products required')
            def fmt(v):
                return ('-' if v<0 else '')+('%0.1f万'%(abs(v)/10000))
            top=y+38; graph_h=410; base=top+230
            max_abs=max(1,max(abs(float(v)) for v in previous+current))
            draw.line((PAD,base,WIDTH-PAD,base),fill='#BCC8D3',width=3)
            for i,label in enumerate(labels):
                xc=PAD+56+i*119
                for j,(v,color) in enumerate(((float(previous[i]),'#5683D8'),(float(current[i]),'#4B9C85'))):
                    h=round(abs(v)/max_abs*188); x=xc+(j*36)-24
                    if v>=0:draw.rounded_rectangle((x,base-h,x+32,base),radius=5,fill=color)
                    else:draw.rounded_rectangle((x,base,x+32,base+h),radius=5,fill=color)
                    val=fmt(v)
                    tw=draw.textlength(val,font=fonts[26]); tx=x+16-tw/2
                    ty=base-h-36 if v>=0 else base+h+4
                    draw.text((tx,ty),val,font=fonts[26],fill='#24394F')
                tw=draw.textlength(str(label),font=fonts[30])
                draw.text((xc-tw/2+6,base+205),str(label),font=fonts[30],fill='#20374B')
            y=top+graph_h+80
            text('■ 前期    ■ 本期  |  标签显示实际金额（万）',26,'#586A7D')
            y+=15
        if card.get('dashboard'):
            dashboard=card['dashboard']; names=['RT','MT','总']; metrics=dashboard['metrics']
            for name in names:
                text(name+'  核心指标',38,'#126F78'); y+=5
                data=dashboard[name]
                for metric in metrics:
                    item=data[metric]
                    text(metric+'：'+str(item['value'])+'  ('+str(item['delta'])+')',30)
                y+=22
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
