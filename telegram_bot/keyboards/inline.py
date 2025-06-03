"""
Inline клавиатуры для Telegram бота
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Optional


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data="action:balance"),
            InlineKeyboardButton(text="📦 Мои аренды", callback_data="action:orders")
        ],
        [
            InlineKeyboardButton(text="🔍 Поиск серверов", callback_data="server:search"),
            InlineKeyboardButton(text="🎯 Охота", callback_data="server:hunt")
        ],
        [
            InlineKeyboardButton(text="🖥️ Мои серверы", callback_data="action:my_servers"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="action:stats")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings:menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_settings_keyboard(has_api_key: bool = False) -> InlineKeyboardMarkup:
    """Меню настроек"""
    keyboard = []
    
    # API ключ
    api_key_text = "✅ API ключ" if has_api_key else "❌ API ключ"
    keyboard.append([
        InlineKeyboardButton(text=api_key_text, callback_data="settings:api_key")
    ])
    
    # Пароли по умолчанию
    keyboard.extend([
        [
            InlineKeyboardButton(text="🔐 SSH пароль", callback_data="settings:ssh_password"),
            InlineKeyboardButton(text="🎫 Jupyter токен", callback_data="settings:jupyter_token")
        ],
        [
            InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings:notifications")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_server_list_keyboard(
    servers: List[Dict[str, Any]], 
    current_page: int = 0,
    total_pages: int = 1,
    selected_servers: Optional[List[int]] = None
) -> InlineKeyboardMarkup:
    """Клавиатура списка серверов с возможностью выбора"""
    if selected_servers is None:
        selected_servers = []
    
    keyboard = []
    
    # Кнопки серверов с чекбоксами
    for server in servers:
        server_id = server.get('id')
        gpu = server.get('specs', {}).get('gpu', 'Unknown')
        price, _ = extract_server_price(server)
        
        # Чекбокс
        check = "✅" if server_id in selected_servers else "⬜"
        
        text = f"{check} #{server_id} | {gpu} | ${price:.2f}/д"
        callback_data = f"select_server:{server_id}"
        
        keyboard.append([
            InlineKeyboardButton(text=text, callback_data=callback_data)
        ])
    
    # Навигация по страницам
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"page:{current_page-1}")
        )
    
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{current_page + 1}/{total_pages}", 
            callback_data="page:current"
        )
    )
    
    if current_page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"page:{current_page+1}")
        )
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Действия
    action_buttons = []
    if selected_servers:
        action_buttons.append(
            InlineKeyboardButton(
                text=f"✅ Арендовать ({len(selected_servers)})", 
                callback_data="action:rent_selected"
            )
        )
    
    action_buttons.append(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="action:refresh")
    )
    action_buttons.append(
        InlineKeyboardButton(text="◀️ Меню", callback_data="main_menu")
    )
    
    keyboard.append(action_buttons)
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_docker_templates_keyboard(templates: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Клавиатура выбора Docker шаблона"""
    keyboard = []
    
    for template in templates[:10]:  # Максимум 10 шаблонов
        name = template.get('name', 'Unnamed')
        category = template.get('category', 'other')
        emoji = {
            'mining': '⛏️',
            'ai': '🤖',
            'rendering': '🎨',
            'computing': '🧮'
        }.get(category, '📦')
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{emoji} {name}",
                callback_data=f"template:{template['id']}"
            )
        ])
    
    keyboard.extend([
        [
            InlineKeyboardButton(text="➕ Создать новый", callback_data="template:create")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_order_details_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для управления заказом"""
    keyboard = [
        [
            InlineKeyboardButton(text="📋 Подробности", callback_data=f"order:details:{order_id}"),
            InlineKeyboardButton(text="📊 Статистика", callback_data=f"order:stats:{order_id}")
        ],
        [
            InlineKeyboardButton(text="🔄 Продлить", callback_data=f"order:extend:{order_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"order:cancel:{order_id}")
        ],
        [
            InlineKeyboardButton(text="◀️ К списку", callback_data="action:orders")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_confirm_keyboard(action: str, data: Any = None) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{action}:{data}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_hunt_settings_keyboard(hunt_task_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Клавиатура настроек охоты"""
    keyboard = []
    
    if hunt_task_id:
        keyboard.extend([
            [
                InlineKeyboardButton(text="▶️ Запустить", callback_data=f"hunt:start:{hunt_task_id}"),
                InlineKeyboardButton(text="⏸️ Пауза", callback_data=f"hunt:pause:{hunt_task_id}")
            ],
            [
                InlineKeyboardButton(text="📝 Изменить", callback_data=f"hunt:edit:{hunt_task_id}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"hunt:delete:{hunt_task_id}")
            ]
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(text="➕ Создать задачу", callback_data="hunt:create")
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_notification_settings_keyboard(user_settings: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Клавиатура настроек уведомлений"""
    sound_enabled = user_settings.get('alert_sound_enabled', True)
    sound_emoji = "🔔" if sound_enabled else "🔕"
    
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"{sound_emoji} Звук: {'Вкл' if sound_enabled else 'Выкл'}",
                callback_data="settings:toggle_sound"
            )
        ],
        [
            InlineKeyboardButton(
                text="💰 Порог баланса",
                callback_data="settings:balance_threshold"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏰ Уведомление об истечении",
                callback_data="settings:expiry_hours"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="settings:menu")
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# Вспомогательная функция из клиента (чтобы не импортировать)
def extract_server_price(server_data: Dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    """Извлечь цену сервера"""
    from config import settings
    
    price_data = server_data.get('price', {})
    
    # Приоритет 1: Цена в USD
    usd_price = price_data.get('usd', {}).get('on_demand_clore')
    if usd_price is not None:
        return usd_price, 'USD'
    
    # Приоритет 2: Фиксированная цена в CLORE
    clore_price = price_data.get('on_demand', {}).get('CLORE-Blockchain')
    if clore_price is not None:
        usd_equivalent = clore_price * settings.clore_to_usd
        return usd_equivalent, 'CLORE_FIXED'
    
    return None, None