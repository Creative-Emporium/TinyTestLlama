import os
import requests
from urllib.request import urlretrieve

class FileDownloader:
    def __init__(self, url, download_path):
        self.url = url
        self.download_path = download_path

    def is_downloadable(self) -> bool:
        try:
            response = requests.head(self.url, allow_redirects=True, timeout=60)
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                print(f"Content-Type: {content_type}")
                non_downloadable_content = ['text', 'image', 'csv', 'octet-stream', 'exe']
                for content in non_downloadable_content:
                    if content in content_type.lower():
                        return False
                return True
            else:
                print(f"HTTP Response Code: {response.status_code}")
                return False
        except requests.RequestException as e:
            print(f"Error: {e}")
            return False

    def download_file(self) -> None:
        try:
            urlretrieve(self.url, self.download_path)
            print(f"File downloaded successfully to: {self.download_path}")
        except Exception as e:
            print(f"Error downloading file: {e}")

    def delete_download(self) -> None:
        try:
            os.remove(self.download_path)
            print(f"File deleted: {self.download_path}")
        except Exception as e:
            print(f"Error deleting file: {e}")

if __name__ == "__main__":
    url = "https://thomashunter.name/media/node-docs/node-v16-docs.pdf"
    download_path = r"C:\Users\DQL1COB\Desktop\example.pdf"

    downloader = FileDownloader(url, download_path)

    if downloader.is_downloadable():
        print(f"The URL {url} is downloadable.")
        downloader.download_file()
    else:
        print(f"The URL {url} is not downloadable.")

    value = input("Enter yes to delete the file downloaded: ")
    if value.lower() == "yes":
        downloader.delete_download()
