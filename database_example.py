import datetime
from database import db, User, Item, ItemStock, EventCategory, Event, EventCostShare

# Open database and create tables (if they don't exist)
db.connect()
db.create_tables([User, Item, ItemStock, EventCategory, Event, EventCostShare])

# Add example users (if they don't exist)
user_maia, _ = User.get_or_create(
    name='Maia',
    defaults={'face_encoding': b"", 'created_at': datetime.datetime.utcnow()}
)

user_jaz, _ = User.get_or_create(
    name='Jaz',
    defaults={'face_encoding': b"", 'created_at': datetime.datetime.utcnow()}
)
user_simon, _ = User.get_or_create(
    name='Simon',
    defaults={'face_encoding': b"", 'created_at': datetime.datetime.utcnow()}
)
user_aldo, _ = User.get_or_create(
    name='Aldo',
    defaults={'face_encoding': b"", 'created_at': datetime.datetime.utcnow()}
)

# Add example categories (if they don't exist)
category_trash, _ = EventCategory.get_or_create(
    name='Trash',
    defaults={'icon': '🗑️', 'created_at': datetime.datetime.utcnow()}
)
category_power, _ = EventCategory.get_or_create(
    name='Power',
    defaults={'icon': '⚡️', 'created_at': datetime.datetime.utcnow()}
)
category_purchases, _ = EventCategory.get_or_create(
    name='Purchases',
    defaults={'icon': '🛍️', 'created_at': datetime.datetime.utcnow()}
)
#CLeanning category
category_cleaning, _ = EventCategory.get_or_create(
    name='Cleaning',
    defaults={'icon': '🧹', 'created_at': datetime.datetime.utcnow()}
)


# Add example items (if they don't exist)
item_toilet_paper, _ = Item.get_or_create(
    name='Toilet paper',
    defaults={'icon': '🧻', 'created_at': datetime.datetime.utcnow()}
)
ItemStock.create(item=item_toilet_paper, stock=0, logged_at=datetime.datetime.utcnow())

# Four examples:
# 1. insert a "took the trash out" event
event = Event.create(
    user=user_aldo,
    category=category_trash,
    photo_path="",
    notes="Took out the trash"
)

# 2. insert a "recharged electricity" event and cost 100$
event = Event.create(
    user=user_aldo,
    category=category_power,
    photo_path="", # <- empty for now
    cost=100,
    notes="Recharged electricity"
)

# The cost will be divided evenly for all the users.
# All of them will pay for the electricity.
users = list(User.select())
for u in users:
    EventCostShare.create(event=event, user=u)

# 3. insert a "bought toilet paper"⁠event. this should set the "toilet paper" item stock to 1.
stock_entry = ItemStock.create(
    item=item_toilet_paper,
    stock=1
)
event = Event.create(
    user=user_aldo,
    category=category_purchases,
    photo_path="",
    cost=500,
    notes="Bought toilet paper",
    stock=stock_entry
)
# The cost will be divided evenly for all the users.
# All of them will pay for the electricity.
users = list(User.select())
for u in users:
    EventCostShare.create(event=event, user=u)

# 4. insert a 'toilet paper is over" event. this should set the “toilet paper” item stock to 0.
stock_entry = ItemStock.create(
    item=item_toilet_paper,
    stock=0
)

event = Event.create(
    user=user_aldo,
    category=category_purchases,
    photo_path="",
    notes="Toilet paper is over",
    stock=stock_entry
)

# Close database before finishing use
db.close()
