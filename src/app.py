import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pychrome
from pypresence import Presence
from pypresence.types import ActivityType


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
    
    def update(self, state, details, large_image, large_text, small_image, small_text, start, end):
        self.rpc.update(
            payload_override = {
                "cmd": "SET_ACTIVITY",
                "args": {
                    "pid": os.getpid(),
                    "activity": {
                        "type": ActivityType.LISTENING.value,
                        "state": state,
                        "details": details,
                        "timestamps": {
                            "start": start,
                            "end": end
                        },
                        "assets": {
                            "large_image": large_image,
                            "large_text": large_text,
                            "small_image": small_image,
                            "small_text": small_text
                        },
                        "instance": True
                    }
                },
                "nonce": '{:.20f}'.format(time.time())
            }
        )
        self.is_showing = True
    
    def clear(self):
        self.rpc.clear()
        self.is_showing = False
    
    def close(self):
        self.rpc.close()
        self.is_showing = False


class Player:
    def __init__(self, title, artist, image, quality, now_time, song_len, status):
        self.title = title
        self.artist = artist
        self.image = image
        self.quality = quality
        self.now_time = now_time
        self.song_len = song_len
        self.status = status


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
    
    def get_player(self):
        title       = self._get_xpath("//span[@class='_inner_16fkr_30']//a")
        artist      = self._get_xpath("//a[@class='_artist_16fkr_45']")
        image       = self._get_xpath("//div[@class='_cover_16fkr_6']//a//img", 'src')
        quality     = self._get_xpath("//a[@class='_icon-link_16fkr_38']//i", 'title')
        now_time    = self._get_xpath("//div[@class='_time-info_czveb_1 _time-info_6q6zi_19']//span[1]")
        song_len    = self._get_xpath("//div[@class='_time-info_czveb_1 _time-info_6q6zi_19']//span[2]")
        play        = self._get_xpath("//button[@class='_button-icon_1h9pm_1 k-icon _opacity-transition_1h9pm_30 k-icon-now_playing-play control']//span[1]")
        pause       = self._get_xpath("//button[@class='_button-icon_1h9pm_1 k-icon _opacity-transition_1h9pm_30 k-icon-now_playing-pause control']//span[1]")
        
        if '' in (title, artist, image, now_time):
            return Player('', '', '', 0, 'paused')
        
        now_time = int(now_time[0]) * 600 + int(now_time[1]) * 60 + int(now_time[3]) * 10 + int(now_time[4])
        song_len = int(song_len[0]) * 600 + int(song_len[1]) * 60 + int(song_len[3]) * 10 + int(song_len[4])
        
        status = None
        if play != '' and pause == '':
            status = 'paused'
        elif play == '' and pause != '':
            status = 'playing'
        
        return Player(title, artist, image, quality, now_time, song_len, status)
    
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
    
    while True:
        try:
            player = app.get_player()
            
            app.logger.info(f'status: {player.status}')
            app.logger.info(f'title: {player.title}')
            app.logger.info(f'artist: {player.artist}')
            app.logger.info(f'quality: {player.quality}')
            app.logger.info(f'now_time: {player.now_time}')
            app.logger.info(f'song_len: {player.song_len}\n')
            
            if player.status == 'playing' and not rpc.is_showing:
                start_time = int(time.time() - player.now_time) * 1000
                end_time = int(time.time() + player.song_len) * 1000
                rpc.update(
                    state       = player.artist,
                    details     = player.title,
                    large_text  = player.quality,
                    large_image = player.image,
                    small_image = 'https://imgur.com/BOIijD9.png',
                    small_text  = 'KKBOX Discord RPC',
                    start       = start_time,
                    end         = end_time,
                )
            elif player.status == 'paused' and rpc.is_showing:
                rpc.clear()
            
        except Exception as e:
            app.logger.error(f'Error: {e}')
            break
        
        time.sleep(1)