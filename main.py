from web3 import Web3, HTTPProvider
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import random
import sys

# Настройки сети Linea
LINEA_RPC_URL = "https://rpc.linea.build"  # Замените на ваш RPC-узел для Linea
GAS_PRICE_GWEI = 20  # Цена газа в Gwei, настройте в зависимости от сети
GAS_LIMIT = 21000  # Стандартный лимит газа для ETH-транзакций
DEFAULT_MIN_DELAY_SECONDS = 5  # Минимальная задержка по умолчанию (секунды)
DEFAULT_MAX_DELAY_SECONDS = 15  # Максимальная задержка по умолчанию (секунды)

# Чтение файлов
def read_file(filename):
    try:
        with open(filename, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        print(f"Ошибка: файл {filename} не найден")
        sys.exit(1)

# Настройка прокси
def create_session(proxy):
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.proxies = {'http': proxy, 'https': proxy}
    return session

# Подключение к Linea
def connect_to_linea(rpc_url, proxy=None):
    try:
        if proxy:
            session = create_session(proxy)
            return Web3(HTTPProvider(rpc_url, session=session))
        return Web3(HTTPProvider(rpc_url))
    except Exception as e:
        print(f"Ошибка подключения к Linea RPC: {e}")
        return None

# Проверка валидности адреса
def is_valid_address(w3, address):
    return w3.is_address(address) and w3.is_checksum_address(address)

# Форматирование приватного ключа
def format_private_key(private_key):
    if not private_key.startswith('0x'):
        return '0x' + private_key
    return private_key

# Отправка ETH
def send_eth(w3, private_key, from_address, to_address, amount_wei):
    try:
        if not is_valid_address(w3, to_address):
            print(f"Ошибка: адрес получателя {to_address} невалиден")
            return False

        # Создание транзакции
        nonce = w3.eth.get_transaction_count(from_address)
        tx = {
            'nonce': nonce,
            'to': to_address,
            'value': amount_wei,
            'gas': GAS_LIMIT,
            'gasPrice': w3.to_wei(GAS_PRICE_GWEI, 'gwei'),
            'chainId': 59144  # Chain ID для Linea mainnet
        }
        
        # Подписание транзакции
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        
        # Отправка транзакции
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"Транзакция отправлена: {tx_hash.hex()}")
        
        # Ожидание подтверждения
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        if receipt.status == 1:
            print(f"Транзакция успешна: {tx_hash.hex()}")
            return True
        else:
            print(f"Транзакция не удалась: {tx_hash.hex()}")
            return False
    except Exception as e:
        print(f"Ошибка при отправке транзакции с {from_address}: {e}")
        return False

def main():
    # Чтение диапазона задержек из аргументов командной строки или использование значений по умолчанию
    try:
        MIN_DELAY_SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MIN_DELAY_SECONDS
        MAX_DELAY_SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_MAX_DELAY_SECONDS
        if MIN_DELAY_SECONDS > MAX_DELAY_SECONDS:
            print("Ошибка: минимальная задержка не может быть больше максимальной")
            sys.exit(1)
        if MIN_DELAY_SECONDS < 0 or MAX_DELAY_SECONDS < 0:
            print("Ошибка: задержки не могут быть отрицательными")
            sys.exit(1)
    except ValueError:
        print("Ошибка: задержки должны быть числами")
        sys.exit(1)

    # Чтение данных из файлов
    private_keys = read_file('private.txt')
    to_addresses = read_file('recipients.txt')
    proxies = read_file('proxy.txt')

    # Проверка на соответствие количества адресов
    if len(private_keys) != len(to_addresses):
        print("Ошибка: количество приватных ключей и адресов получателей не совпадает")
        sys.exit(1)

    # Подключение к Linea
    for i, (private_key, to_address) in enumerate(zip(private_keys, to_addresses)):
        proxy = proxies[i % len(proxies)] if proxies else None
        w3 = connect_to_linea(LINEA_RPC_URL, proxy)
        
        if not w3 or not w3.is_connected():
            print(f"Ошибка: не удалось подключиться к Linea RPC через прокси {proxy}")
            continue
        
        # Форматирование приватного ключа
        private_key = format_private_key(private_key)
        
        # Получение адреса отправителя из приватного ключа
        try:
            account = w3.eth.account.from_key(private_key)
            from_address = account.address
        except Exception as e:
            print(f"Ошибка: некорректный приватный ключ для кошелька {i+1}: {e}")
            continue
        
        # Проверка баланса
        balance = w3.eth.get_balance(from_address)
        if balance <= w3.to_wei(0.001, 'ether'):  # Минимальный баланс для транзакции
            print(f"Недостаточно средств на кошельке {from_address} ({w3.from_wei(balance, 'ether')} ETH)")
            continue
        
        # Вывод всего баланса за вычетом газа
        gas_cost = GAS_LIMIT * w3.to_wei(GAS_PRICE_GWEI, 'gwei')
        amount_to_send = balance - gas_cost
        
        if amount_to_send <= 0:
            print(f"Недостаточно средств для оплаты газа на кошельке {from_address} ({w3.from_wei(balance, 'ether')} ETH)")
            continue
        
        print(f"Отправка {w3.from_wei(amount_to_send, 'ether')} ETH с {from_address} на {to_address} через прокси {proxy}")
        success = send_eth(w3, private_key, from_address, to_address, amount_to_send)
        
        # Случайная задержка между транзакциями
        if success and i < len(private_keys) - 1:  # Не добавлять задержку после последней транзакции
            delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
            print(f"Ожидание {delay:.2f} секунд перед следующей транзакцией...")
            time.sleep(delay)

if __name__ == "__main__":
    main()
