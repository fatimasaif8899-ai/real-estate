from pathlib import Path
from database import get_db_connection
from werkzeug.security import generate_password_hash
ROOT=Path(__file__).resolve().parent
COVER_DIR=ROOT/'static'/'uploads'/'covers'; COVER_DIR.mkdir(parents=True,exist_ok=True)
def make_cover(filename,title,author,bg,accent,icon):
    title=title.replace('&','&amp;')
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="700" height="1050"><rect width="700" height="1050" rx="36" fill="{bg}"/><circle cx="560" cy="150" r="110" fill="{accent}" opacity=".28"/><circle cx="120" cy="880" r="150" fill="{accent}" opacity=".18"/><path d="M70 210 Q350 90 630 210" fill="none" stroke="{accent}" stroke-width="12" stroke-linecap="round"/><text x="350" y="130" text-anchor="middle" font-family="Georgia" font-size="28" fill="{accent}">LUMORA STORY EDITION</text><text x="350" y="470" text-anchor="middle" font-family="Georgia" font-weight="700" font-size="58" fill="#fffdf8">{title}</text><text x="350" y="545" text-anchor="middle" font-family="Arial" font-size="28" fill="#fffdf8">{author}</text><text x="350" y="760" text-anchor="middle" font-size="170">{icon}</text><path d="M100 920 Q350 850 600 920" fill="none" stroke="#fffdf8" stroke-width="5" opacity=".7"/><text x="350" y="980" text-anchor="middle" font-family="Arial" font-size="22" fill="#fffdf8">A little book for a big imagination</text></svg>'''
    (COVER_DIR/filename).write_text(svg,encoding='utf-8')
def seed():
    conn=get_db_connection()
    if not conn: print('Database unavailable. Run schema.sql first.'); return
    cur=conn.cursor()
    cur.execute('SELECT id FROM users WHERE email=%s',('admin@lumora.lib',))
    if not cur.fetchone(): cur.execute("INSERT INTO users(name,email,password_hash,role) VALUES(%s,%s,%s,'admin')",('LUMORA Keeper','admin@lumora.lib',generate_password_hash('Admin123!')))
    for key,value in [('site_title','LUMORA'),('library_desc','Where stories find their light.')]: cur.execute("INSERT INTO site_settings(setting_key,setting_value) VALUES(%s,%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",(key,value))
    cats=[("Children's Stories",'children-stories'),('Urdu Novels','urdu-novels'),('English Novels','english-novels'),('Romance','romance'),('Mystery & Detective','mystery'),('Fantasy & Magic','fantasy'),('Adventure','adventure'),('Poetry','poetry'),('Classic Fiction','classic-fiction'),('Philosophy','philosophy'),('Horror & Gothic','horror-gothic'),('Young Adult','young-adult'),('History','history'),('Science','science'),('Self Growth','self-growth')]
    ids={}
    for name,slug in cats:
        cur.execute('INSERT INTO categories(name,slug,illustration) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name)',(name,slug,'')); cur.execute('SELECT id FROM categories WHERE slug=%s',(slug,)); ids[slug]=cur.fetchone()[0]
    def author(name):
        cur.execute('SELECT id FROM authors WHERE name=%s',(name,)); r=cur.fetchone()
        if r:return r[0]
        cur.execute('INSERT INTO authors(name) VALUES(%s)',(name,)); return cur.lastrowid
    def source(name,url):
        cur.execute('SELECT id FROM sources WHERE name=%s',(name,)); r=cur.fetchone()
        if r:return r[0]
        cur.execute('INSERT INTO sources(name,url_base) VALUES(%s,%s)',(name,url)); return cur.lastrowid
    names=['Jane Austen','Mary Shelley','Lewis Carroll','Charlotte Brontë','Oscar Wilde','Emily Dickinson','Plato','Robert Louis Stevenson','Mark Twain','Louisa May Alcott','Miguel de Cervantes','Bram Stoker','Arthur Conan Doyle','Rabindranath Tagore','Saadat Hasan Manto','L. Frank Baum','Homer']
    authors={n:author(n) for n in names}; src=source('Project Gutenberg','https://www.gutenberg.org')
    books=[
    ('Pride and Prejudice','Jane Austen',1813,'English','classic-fiction romance','austen.svg','#7b547d','#f2b7c9','♡'),('Frankenstein','Mary Shelley',1818,'English','classic-fiction horror-gothic','frankenstein.svg','#304b46','#a9e4d1','⚡'),("Alice's Adventures in Wonderland",'Lewis Carroll',1865,'English','children-stories fantasy adventure','alice.svg','#4c6692','#ffd76a','♠'),('Jane Eyre','Charlotte Brontë',1847,'English','english-novels romance classic-fiction','jane-eyre.svg','#72516a','#d8b7f5','🌹'),('The Picture of Dorian Gray','Oscar Wilde',1890,'English','classic-fiction horror-gothic','dorian.svg','#56415e','#ffb0c7','🪞'),("A Child's Garden of Verses",'Robert Louis Stevenson',1885,'English','children-stories poetry','child-verses.svg','#5d7d73','#ffe19a','☁'),('The Wonderful Wizard of Oz','L. Frank Baum',1900,'English','children-stories fantasy adventure','wizard-oz.svg','#7b6b9e','#f7d35f','🧙'),('Little Women','Louisa May Alcott',1868,'English','english-novels romance young-adult','little-women.svg','#8a5b5f','#f5c4d3','🌸'),('The Adventures of Sherlock Holmes','Arthur Conan Doyle',1892,'English','mystery adventure classic-fiction','sherlock.svg','#4c5c68','#e7c77a','🔎'),('The Adventures of Tom Sawyer','Mark Twain',1876,'English','adventure young-adult classic-fiction','tom-sawyer.svg','#557a88','#f3c17a','⛵'),('The Odyssey','Homer',-700,'English','adventure classic-fiction history','odyssey.svg','#3f5e73','#b5d8e8','⚓'),('The Republic','Plato',-375,'English','philosophy history','republic.svg','#6d5b79','#d8c4ef','☁'),('Poems of Emily Dickinson','Emily Dickinson',1890,'English','poetry','dickinson.svg','#657c91','#e8c8df','✒'),('Dracula','Bram Stoker',1897,'English','horror-gothic classic-fiction','dracula.svg','#3d303c','#d96a8b','🦇'),('Don Quixote','Miguel de Cervantes',1605,'English','adventure classic-fiction','quixote.svg','#8a684b','#e6c16e','⚔'),('The Happy Prince','Oscar Wilde',1888,'English','children-stories poetry','happy-prince.svg','#55706b','#f2cf69','🕊'),('Selected Stories','Saadat Hasan Manto',1948,'Urdu','urdu-novels classic-fiction','manto.svg','#66517d','#e5a6c1','✦'),('Gitanjali','Rabindranath Tagore',1910,'English','poetry philosophy','gitanjali.svg','#536b63','#e9c36f','🌿')]
    featured={'Pride and Prejudice',"Alice's Adventures in Wonderland",'Frankenstein','Jane Eyre','The Wonderful Wizard of Oz','Selected Stories'}
    gutenberg={
      'Pride and Prejudice':1342,'Frankenstein':84,"Alice's Adventures in Wonderland":11,'Jane Eyre':1260,'The Picture of Dorian Gray':174,"A Child's Garden of Verses":256,'The Wonderful Wizard of Oz':55,'Little Women':514,'The Adventures of Sherlock Holmes':1661,'The Adventures of Tom Sawyer':74,'The Odyssey':1727,'The Republic':1497,'Dracula':345,'Don Quixote':996,'The Happy Prince':902,'Gitanjali':716
    }
    for title,an,year,lang,slugs,cover,bg,accent,icon in books:
        make_cover(cover,title,an,bg,accent,icon); aid=authors[an]; url=f'/static/uploads/covers/{cover}'; desc=f'A LUMORA illustrated shelf edition of {title}, ready to discover, save and revisit.'
        cur.execute('SELECT id FROM books WHERE title=%s AND author_id=%s',(title,aid)); row=cur.fetchone()
        gid=gutenberg.get(title)
        read_url=f'https://www.gutenberg.org/ebooks/{gid}' if gid else ''
        pdf_url=f'https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.pdf' if gid else ''
        if row: bid=row[0]; cur.execute('UPDATE books SET description=%s,cover_url=%s,pub_year=%s,language=%s,is_featured=%s,read_url=%s,pdf_url=%s WHERE id=%s',(desc,url,year,lang,title in featured,read_url,pdf_url,bid))
        else: cur.execute("INSERT INTO books(title,author_id,description,cover_url,pub_year,language,source_id,license_info,is_featured,read_url,pdf_url) VALUES(%s,%s,%s,%s,%s,%s,%s,'Public Domain',%s,%s,%s)",(title,aid,desc,url,year,lang,src,title in featured,read_url,pdf_url)); bid=cur.lastrowid
        cur.execute('DELETE FROM book_categories WHERE book_id=%s',(bid,))
        for slug in slugs.split(): cur.execute('INSERT IGNORE INTO book_categories(book_id,category_id) VALUES(%s,%s)',(bid,ids[slug]))
    conn.commit(); cur.close(); conn.close(); print('LUMORA story garden seeded successfully.')
if __name__=='__main__': seed()
