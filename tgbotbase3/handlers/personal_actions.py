import structlog
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext  
from aiogram.fsm.state import State, StatesGroup  
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pydantic import BaseModel
import asyncio, random, aiomysql
from datetime import datetime
from aiogram import Bot
from typing import Optional
from decimal import Decimal

from fluent.runtime import FluentLocalization

# Declare router
router = Router()
bot = Bot(token="7857559139:AAHCFir0za6XOG7q0T8OAI5qaR0WXF-bd8E")
router.message.filter(F.chat.type == "private")

class Ticket(BaseModel):
    ticket_id: Optional[int]
    user_id: int
    issue_description: str
    status: str
    created_at: datetime

class UserStates(StatesGroup):
    waiting_for_order_id = State()
    waiting_for_payment_confirmation = State()
    
    waiting_for_explain_problem = State()
    waiting_for_support_answer = State()
    waiting_for_support_resolution = State()

# Declare logger
logger = structlog.get_logger()

async def connect_to_website_db():
    pool = await aiomysql.create_pool(
        host='localhost',
        user='sitedata',
        password='871455Ork',
        db='sitedata',
        autocommit=True
    )
    return pool

async def get_db_connection():
    pool = await aiomysql.create_pool(
        host='localhost',
        user='sql_support_msk5',
        password='clbiwz95yryqiihm',
        db='sql_support_msk5',
        autocommit=True
    )
    return pool

async def get_all_tickets_from_db():
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM tickets WHERE status != 'Answered';")
            result = await cursor.fetchall()
            return result

# Fix: make the function async and change its logic
async def insert_ticket_to_DB(ticket: Ticket):
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO tickets (user_id, issue_description, status) VALUES (%s, %s, %s)",
                (ticket.user_id, ticket.issue_description, ticket.status)
            )
            ticket_id = cursor.lastrowid  
            return ticket_id

# Declare handlers
@router.message(Command("start"))
async def cmd_owner_hello(message: Message, l10n: FluentLocalization):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard = [
            [InlineKeyboardButton(text="Оплатить заказ", callback_data="OrderPay_call")],
            [InlineKeyboardButton(text="Поддержка", callback_data="Support_call")],
        ]    
    )
    await message.answer(l10n.format_value("hello-msg"), reply_markup=keyboard)

@router.callback_query(F.data=="OrderPay_call")
async def reply_order_pay(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.answer("Напишите ID своего заказа:")
    await state.set_state(UserStates.waiting_for_order_id)
    
@router.callback_query(F.data=="pay_cancel")
async def cancel_order_pay(callback_query: CallbackQuery):
    await trigger_offer_option_to_user(callback_query=callback_query)
    
@router.message(UserStates.waiting_for_order_id)
async def reply_on_user_order_id(message: Message, state: FSMContext):
    user_reply = message.text
    await asyncio.sleep(1)
    await state.set_state(UserStates.waiting_for_payment_confirmation)
    await state.update_data(user_reply=user_reply)
    pool = await connect_to_website_db()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT * FROM smartzamovapp_order WHERE id=%s",(user_reply, ))
            result = await cursor.fetchone()
            
    if result and result[5]==0:
        if result[12] == result[9]:
            currency = "руб"
            amount = int(result[12]/Decimal("1.7"))
        elif result[11] == result[9]:
            currency = "$"
            amount = int(result[11]/Decimal("0.019"))
        elif result[10] == result[9]:
            currency = "€"
            amount = int(result[10]/Decimal("0.01764"))
        await message.answer(f"Заказ с ID **{user_reply}** найден!\nК оплате: {result[9]} {currency}.", parse_mode="Markdown")
        kb = InlineKeyboardBuilder()
        kb.button(
            text=f"Оплатить {amount} XTR",
            pay=True
        )
        kb.button(
            text=("Отменить операцию"),
            callback_data="pay_cancel"
        )
        kb.adjust(1)
        
        prices = [LabeledPrice(label="XTR", amount=amount)]
        
        await message.answer_invoice(
            title=(f"Оплата заказа {user_reply}"),
            description = f"К оплате: {result[9]} {currency}. (Сумма оплаты: {amount} звёзд)",
            prices=prices,
            
            provider_token="",
    
            payload=f"{amount}_stars",
    
            currency="XTR",
    
            reply_markup=kb.as_markup()
        )
    else:
        if result and result[5]==1:
            await message.answer(f"Заказ с данным ID: **{user_reply}** уже оплачен.", parse_mode="Markdown")
        else:
            await message.answer(f"По данному ID: **{user_reply}** . Не найдено заказа :(", parse_mode="Markdown")
        await state.clear()
        await trigger_offer_option_to_user(message=message)

@router.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment_complete(message: Message, state: FSMContext):
    await asyncio.sleep(1)
    data = await state.get_data()
    user_reply = data.get("user_reply")
    await message.answer("Платёж успешно проведён! 🎉", message_effect_id="5046509860389126442")
    pool = await connect_to_website_db()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE smartzamovapp_order SET is_paid=1 WHERE id=%s", (user_reply,))
    await state.clear()

async def trigger_offer_option_to_user(message: Message = None, callback_query: CallbackQuery = None):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard = [
            [InlineKeyboardButton(text="Оплатить заказ", callback_data="OrderPay_call")],
            [InlineKeyboardButton(text="Поддержка", callback_data="Support_call")],
        ]    
    )
    if message:
        await message.answer("Что вас интересует?", reply_markup=keyboard)
    else:
        await callback_query.message.answer("Что вас интересует?", reply_markup=keyboard)
    
@router.callback_query(F.data=="Support_call")
async def reply_to_user_about_help(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.message.answer("Опишите проблему с которой столкнулись")
    await state.set_state(UserStates.waiting_for_explain_problem)

@router.message(UserStates.waiting_for_explain_problem)
async def get_user_problem(message: Message, state: FSMContext):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    text_message = message.text
    new_ticket = Ticket(ticket_id=None, user_id=user_id, issue_description=message.text, status="Opened", created_at=datetime.now())
    ticket_id = await insert_ticket_to_DB(new_ticket)
    support_chat_ids = [624349412, 1639670525]
    
    await message.answer(f"Ваш тикет #{ticket_id} успешно создан. Ожидайте ответа. Он прийдёт вам в этот чат")
    await state.clear()
    await trigger_offer_option_to_user(message=message)
    
    for chat_id in support_chat_ids:
        await bot.send_message(chat_id, f"Новый тикет #{ticket_id} от пользователя {full_name}. Проблема: {text_message}")
    
@router.message(Command("reply_ticket"))
async def reply_to_ticket(message: Message, state: FSMContext):
    support_chat_ids = [624349412, 1639670525]
    if message.from_user.id not in support_chat_ids:
        await message.answer("У вас нет соотвецтвующих прав!")
        return
    
    try:
        ticket_id = int(message.text.split()[1])
        reply_on_ticket = " ".join(message.text.split()[2:])
    except:
        await message.answer("Форма не правильно заполнена!")
        return

    # Обновляем статус тикета в базе данных
    pool = await get_db_connection()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("UPDATE tickets SET status='Answered' WHERE ticket_id=%s", (ticket_id,))
            await cursor.execute("SELECT user_id,issue_description  FROM tickets WHERE ticket_id=%s", (ticket_id, ))
            result = await cursor.fetchone()
            
            if result:
                user_id = result[0]
                problem_desc = result[1]
                await bot.send_message(user_id, f"Тикет ID: #{ticket_id}\nПроблема в тикете: {problem_desc}\nОтвет: {reply_on_ticket}")
                await message.answer(f"Ответ на тикет #{ticket_id} успешно отправлен пользователю.")
            else:
                await message.answer(f"Ошибка: Тикет #{ticket_id} не найден.")

@router.message(Command("view_all_tickets"))
async def view_all_tickets(message: Message):
    support_chat_ids = [624349412, 1639670525]
    if message.from_user.id not in support_chat_ids:
        await message.answer("У вас нет соотвецтвующих прав!")
        return
    
    all_tickets = await get_all_tickets_from_db()
    tickets_text = "Список всех тикетов:\n\n"
    if all_tickets:
        for i, ticket in enumerate(all_tickets):
            if i == len(all_tickets) - 1:
                tickets_text += f"Тикет #{ticket[0]} (Пользователь: {ticket[1]}): {ticket[2]} - Статус: {ticket[3]}\n\n"
            else:
                tickets_text += f"Тикет #{ticket[0]} (Пользователь: {ticket[1]}): {ticket[2]} - Статус: {ticket[3]}\n"
        tickets_text += "Формат ответа на тикет: /reply_ticket айди тикета Ответ на тикет"
    else:
        tickets_text = "Нет открытых тикетов."
    
    await message.answer(tickets_text)
    
@router.message(Command("answer_format"))
async def type_answer_format(message: Message):
    support_chat_ids = [624349412, 1639670525]
    if message.from_user.id not in support_chat_ids:
        await message.answer("У вас нет соотвецтвующих прав!")
        return
    await message.answer("Напишите ваш ответ в таком формате (после каждого значения 1 пробел): /reply_ticket   айди_тикета   Ответ_на_тикет")
    