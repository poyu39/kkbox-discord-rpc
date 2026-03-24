import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psutil
import pychrome
from pypresence import Presence
from pypresence.types import ActivityType


class Player:
    def __init__(self, title=None, artist=None, track_url=None, image=None, quality=None, now_time=None, song_len=None, status=None):
        self.title = title
        self.artist = artist
        self.track_url = track_url
        self.image = image
        self.quality = quality
        self.now_time = now_time
        self.song_len = song_len
        self.status = status
    
    def print_info(self, logger: logging.Logger):
        logger.info(f'status: {self.status}')
        logger.info(f'title: {self.title}')
        logger.info(f'artist: {self.artist}')
        logger.info(f'quality: {self.quality}')
        logger.info(f'now_time: {self.now_time}')
        logger.info(f'song_len: {self.song_len}')
        logger.info(f'track_url: {self.track_url}')
        logger.info(f'image: {self.image}\n')
    
    def have_empty(self):
        required_text_fields = [self.title, self.artist, self.track_url, self.image]
        has_empty_text = any((not isinstance(field, str)) or (not field.strip()) for field in required_text_fields)
        
        invalid_time = (
            not isinstance(self.now_time, int) or self.now_time < 0 or
            not isinstance(self.song_len, int) or self.song_len <= 0
        )
        
        return has_empty_text or invalid_time


class DiscordRPC:
    def __init__(self, application_id):
        self.rpc = Presence(application_id)
        self.is_showing = False
    
    def connect(self):
        try:
            self.rpc.connect()
            return True
        except Exception as e:
            return False
    
    def _normalize_http_url(self, value: str | None):
        if not isinstance(value, str):
            return None
        
        candidate = value.strip()
        if not candidate:
            return None
        
        if candidate.startswith('//'):
            candidate = f'https:{candidate}'
        elif candidate.startswith('/'):
            candidate = f'https://play.kkbox.com{candidate}'
        
        parsed = urlsplit(candidate)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            return None
        
        safe_path = quote(parsed.path or '/', safe='/%:@-._~!$&\'()*+,;=')
        safe_query = quote(parsed.query, safe='=&:@-._~!$\'()*+,;/?')
        return urlunsplit((parsed.scheme, parsed.netloc, safe_path, safe_query, ''))
    
    def update(self, player: Player):
        large_url = self._normalize_http_url(player.track_url)
        assets = {
            'large_image': player.image,
            'large_text': player.quality if player.quality else 'No Quality',
            'small_image': 'https://github.com/poyu39/kkbox-discord-rpc/blob/main/media/icon_128.png?raw=true',
            'small_text': 'KKBOX Discord RPC',
            'small_url': 'https://github.com/poyu39/kkbox-discord-rpc'
        }
        if large_url:
            assets['large_url'] = large_url
        
        start_time = time.time() - player.now_time
        end_time = start_time + player.song_len
        self.rpc.update(
            payload_override = {
                'cmd': 'SET_ACTIVITY',
                'args': {
                    'pid': os.getpid(),
                    'activity': {
                        'type': ActivityType.LISTENING.value,
                        'state': player.artist,
                        'details': player.title,
                        'timestamps': {
                            'start': int(start_time) * 1000,
                            'end': int(end_time) * 1000
                        },
                        'assets': assets,
                        'instance': True
                    }
                },
                'nonce': '{:.20f}'.format(time.time())
            }
        )
        self.is_showing = True
        return True
    
    def clear(self):
        self.rpc.clear()
        self.is_showing = False
    
    def close(self):
        self.rpc.close()
        self.is_showing = False


class KKBOX:
    def __init__(self, kkbox_exe_path, port=9239):
        self.kkbox_exe_path = kkbox_exe_path
        self.port = port
        self.browser = None
        self.tab = None
        self.kkbox_process = None
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        logging.getLogger('pychrome.tab').setLevel(logging.CRITICAL)
        
        self.logger = logging.getLogger(__name__)
    
    def start_kkbox(self):
        cwd = f'{os.path.dirname(self.kkbox_exe_path)}/discord_rpc'
        if os.path.exists(cwd):
            shutil.rmtree(cwd)
        os.makedirs(cwd, exist_ok=True)
        
        self.kkbox_process = subprocess.Popen(
            [
                self.kkbox_exe_path,
                f'--remote-debugging-port={self.port}',
            ],
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(5)
    
    def start_browser(self):
        try:
            self.browser = pychrome.Browser(url=f'http://127.0.0.1:{self.port}')
            self.tab = self.browser.list_tab()[0]
            self.tab.start()
            self.tab.Network.enable()
            self.tab.Page.enable()
        except Exception as e:
            self.logger.error('connect to KKBOX failed')
            sys.exit(1)
    
    def is_kkbox_running(self):
        if self.kkbox_process.poll() is not None:
            return False
        
        for proc in psutil.process_iter(['pid', 'name']):
            if 'KKBOX' in proc.info['name']:
                return True
        return False
    
    def _parse_mm_ss(self, value):
        if not isinstance(value, str):
            return None
        
        value = value.strip()
        parts = value.split(':')
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            return None
        
        minutes, seconds = map(int, parts)
        if seconds >= 60:
            return None
        
        return minutes * 60 + seconds
    
    def get_player(self):
        player_data = self._get_player_dom_data()
        
        title = player_data.get('title')
        artist = player_data.get('artist')
        track_url = player_data.get('track_url')
        image = player_data.get('image')
        quality = player_data.get('quality')
        now_time = self._parse_mm_ss(player_data.get('now_time'))
        song_len = self._parse_mm_ss(player_data.get('song_len'))
        status = player_data.get('status')
        
        if track_url:
            track_url = track_url.replace('http://localhost:55680/', 'https://play.kkbox.com/')
        
        return Player(title, artist, track_url, image, quality, now_time, song_len, status)
    
    def _get_player_dom_data(self) -> dict:
        evaluate_func = '''
            (() => {
                const pick = (selectors, attr = null) => {
                    for (const selector of selectors) {
                        const el = document.querySelector(selector);
                        if (!el) continue;
                        
                        if (!attr) {
                            const value = (el.textContent || '').trim();
                            if (value) return value;
                            continue;
                        }
                        
                        const value = (el.getAttribute(attr) || '').trim();
                        if (value) return value;
                    }
                    return '';
                };
                
                const title = pick([
                    'div[class*="_media-info_"] div[class*="_name_"] a[href*="/track/"]',
                    'div[class*="_media-info_"] a[href*="/track/"]'
                ]);
                
                const trackUrl = pick([
                    'div[class*="_media-info_"] div[class*="_name_"] a[href*="/track/"]',
                    'div[class*="_media-info_"] div[class*="_cover_"] a[href*="/track/"]',
                    'div[class*="_media-info_"] a[href*="/track/"]'
                ], 'href');
                
                const artist = pick([
                    'div[class*="_media-info_"] a[href*="/artist/"]'
                ]);
                
                const image = pick([
                    'div[class*="_media-info_"] div[class*="_cover_"] img',
                    'div[class*="_media-info_"] img'
                ], 'src');
                
                const quality = pick([
                    'div[class*="_media-info_"] [class*="_icon-link_"] i[title]',
                    'div[class*="_media-info_"] i[title]'
                ], 'title');
                
                const timeSpans = Array.from((document.querySelector('div[class*="_time-info_"]') || document).querySelectorAll('span'));
                const nowTime = timeSpans[0] ? (timeSpans[0].textContent || '').trim() : '';
                const songLen = timeSpans[1] ? (timeSpans[1].textContent || '').trim() : '';
                
                return {
                    title,
                    artist,
                    track_url: trackUrl,
                    image,
                    quality,
                    now_time: nowTime,
                    song_len: songLen,
                    status: null,
                };
            })();
        '''
        
        result = self.tab.Runtime.evaluate(expression=evaluate_func, returnByValue=True)
        return result.get('result', {}).get('value', {})
    
    def _get_xpath(self, xpath, attr='innerText'):
        xpath_func = f'''
            (function() {{
                let result = document.evaluate("{xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                return result.singleNodeValue ? result.singleNodeValue.{attr} : '';
            }})();
        '''
        return self.tab.Runtime.evaluate(expression=xpath_func)['result']['value']


if __name__ == '__main__':
    kkbox_exe_path = Path(f'{os.getenv("USERPROFILE")}/AppData/Local/Programs/@universalelectron-shell/KKBOX.exe')
    
    app = KKBOX(kkbox_exe_path)
    rpc = DiscordRPC('1017636675817578538')
    
    app.start_kkbox()
    app.start_browser()
    
    if rpc.connect():
        app.logger.info('Discord RPC connected successfully')
    else:
        app.logger.error('Discord RPC connection failed')
        sys.exit(1)
    
    last_song = None
    last_now_time = None
    last_status = 'paused'
    
    while True:
        try:
            player = app.get_player()
            
            if player.have_empty():
                continue
            
            if player.status not in ('playing', 'paused'):
                if last_song != player.title:
                    player.status = 'playing'
                elif last_now_time is None:
                    player.status = last_status
                else:
                    player.status = 'playing' if player.now_time != last_now_time else 'paused'
            
            need_refresh_rpc = (last_song != player.title) or (last_status != player.status)
            
            if need_refresh_rpc and player.status == 'playing':
                if rpc.update(player):
                    player.print_info(logger=app.logger)
            
            elif need_refresh_rpc and player.status == 'paused':
                player.print_info(logger=app.logger)
                rpc.clear()
            
            last_song = player.title
            last_now_time = player.now_time
            last_status = player.status
        
        except Exception as e:
            app.logger.error(f'Error: {e}')
            break
        
        time.sleep(1)