from aiogram.fsm.state import State, StatesGroup

class SubscribeState(StatesGroup):  # Класс для чтения сообщений без команды (после команды в предыдущем сообщении)
    waiting_for_symbol = State()