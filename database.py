from peewee import IntegerField, Model, SqliteDatabase, CharField, ForeignKeyField, TextField, BlobField, DateTimeField, DecimalField, AutoField, DateField
import datetime
from datetime import date

#create an instance of the database
db = SqliteDatabase('my_database.db')


# Field instance --> column of the table
# Model instance --> row of the table

class BaseModel(Model):
    class Meta:
        database = db #to specify the tables to use this database

#--------------Tables definition--------------
#USER TABLE
class User(BaseModel):
    name = CharField(unique=True)
    face_encoding = BlobField()
    created_at = DateTimeField(default=datetime.datetime.utcnow)

#ITEM TABLE   
class Item(BaseModel):
    name = CharField()
    icon = CharField()
    created_at = DateTimeField(default=datetime.datetime.utcnow)

#TABLE FOR NUMBER OF ITEMS
class ItemStock(BaseModel):
    #this filed connects to the Item Table 
    item = ForeignKeyField(Item, backref='stocks', on_delete='CASCADE')
    stock = IntegerField()
    logged_at = DateTimeField(default=datetime.datetime.utcnow)

#TABLE FOR TYPE OF EVENTS: power, purchases, trash
class EventCategory(BaseModel):
    name = CharField(unique=True)
    icon = CharField()
    created_at = DateTimeField(default=datetime.datetime.now)

#TABLE FOR THE ACTIONS/EVENTS
class Event(BaseModel):
    #connects to the user who perfomred the event 
    user = ForeignKeyField(User, backref='events', on_delete='CASCADE')
    category = ForeignKeyField(EventCategory, backref='events', on_delete='CASCADE')
    #whent the event was performed
    logged_at = DateTimeField(default=datetime.datetime.now)
    #when the event was last modified
    modified_at = DateTimeField(default=datetime.datetime.now)
    photo_path = TextField()
    #optional cost field
    cost = DecimalField(10, 2, null=True)
    #foreign key to Item stock
    stock = ForeignKeyField(ItemStock, backref='event', null=True, unique=True, on_delete='CASCADE')
    notes = TextField(default="") 

# If the event has a cost, who should pay for this event?
# There can be multiple per event, and the cost is divided evenly between the people.
class EventCostShare(BaseModel):
    event = ForeignKeyField(Event, backref='cost_shared_among', on_delete='CASCADE')
    # Vincula este registro a un 'Event' específico.
    # 'backref='cost_shared_among'' te permite hacer `event.cost_shared_among`
    # para ver todos los registros (y usuarios) que comparten el costo de ese evento.
    user = ForeignKeyField(User, backref='events_cost_shared', on_delete='CASCADE')
    # Vincula este registro a un 'User' específico (el que tiene que pagar su parte).
    # 'backref='events_cost_shared'' te permite hacer `user.events_cost_shared`
    # para ver todos los costos de eventos que este usuario debe pagar


# Template
class EventTemplate(BaseModel):
    category = ForeignKeyField(EventCategory, backref='templates', on_delete='CASCADE')
    cost = DecimalField(10, 2, null=True)
    notes = TextField(default="")

# Separate table to not add 2 nullable fields requiring double manual NOT NULL check
class EventTemplateItemStock(BaseModel):
    template = ForeignKeyField(EventTemplate, backref='stock', on_delete='CASCADE')
    item = ForeignKeyField(Item, backref='event_template_item_stocks', on_delete='CASCADE')
    stock = IntegerField()


#--------------PARTE DE JAZ
class CleaningLog(BaseModel):
    id = AutoField()
    user = ForeignKeyField(User, backref='cleanings', on_delete='CASCADE')
    date = DateField(default=date.today)