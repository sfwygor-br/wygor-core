import requests

def main():
	response = requests.get('https://api.openweathermap.org/data/2.5/weather?q=London&appid=YOUR_API_KEY')
	print(response.json())