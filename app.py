from flask import Flask, render_template_string, request, jsonify
#import tables from db
from database import db, User, Item, ItemStock, EventCategory, Event, EventTemplate, EventTemplateItemStock, CleaningLog
import face_recognition
import numpy as np
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, date
from decimal import Decimal

#flask application instance
app = Flask(__name__)
#where photos uploaded by users are stored
app.config['UPLOAD_FOLDER'] = 'uploads'
#maximum file size
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
#creates upload folder if not created yet
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

TRASH_CATEGORY_NAME = 'Trash'
CLEANING_CATEGORY_NAME = 'Room Cleaning'
ROTATION_DAY_OF_WEEK = 5 # 5 = Sábado. La rotación avanza cada Sábado


#--------------DATABASE INITIALIZATION--------------
# Initialize database and create default category/template
def init_db():

    
    db.connect(reuse_if_open=True) #connects to .db file
    #creates table if they dont exist
    db.create_tables([User, Item, ItemStock, EventCategory, Event, EventTemplate, EventTemplateItemStock, CleaningLog])
    
    # Create default category if not exists
    default_category, _ = EventCategory.get_or_create(
        name='Default',
        defaults={'icon': '📋', 'created_at': datetime.now()}
    )
    
    # Create default template if not exists
    EventTemplate.get_or_create(
        category=default_category,
        defaults={'cost': None, 'notes': ''}
    )
    
    db.close() #close connection temporarily

init_db() #runs initialization


# --- PARTE DE JAZ: Busca el ID del último usuario que limpió en CleaningLog para iniciar la rotación ---

def get_last_cleaner_id():
    try:
        last_log = CleaningLog.select().order_by(CleaningLog.date.desc()).first()
        return last_log.user_id if last_log else 0
    except Exception:
        # Maneja el caso en que la tabla esté vacía
        return 0


def get_cleaning_schedule(weeks=6):
    db.connect(reuse_if_open=True)
    users = list(User.select().order_by(User.id)) # Obtiene usuarios ordenados para el orden de rotacion
    if not users:
        db.close()
        return []
    
    last_cleaner_id = get_last_cleaner_id() 
    user_ids = [u.id for u in users]
    
    # Determina el punto de inicio de la rotación
    try:
        # Encuentra quién es el siguiente después del último limpiador
        last_index = user_ids.index(last_cleaner_id)
        current_cleaner_index = (last_index + 1) % len(users) 
    except ValueError:
        current_cleaner_index = 0
        
    #  Calcula la fecha de la próxima rotación (próximo Sábado)
    today = datetime.now().date()
    days_until_rotation = (ROTATION_DAY_OF_WEEK - today.weekday() + 7) % 7
    next_rotation_date = today + timedelta(days=days_until_rotation)

    # Ajuste: Si ya es Sábado  y pasó el mediodía, la rotación empieza la próxima semana
    if days_until_rotation == 0 and datetime.now().hour >= 12: 
         next_rotation_date += timedelta(days=7)
    
    schedule = []
    
    # Genera el calendario de las próximas N semanas
    for i in range(weeks):
        rotation_date = next_rotation_date + timedelta(weeks=i)
        cleaner_user = users[current_cleaner_index]
        
        schedule.append({
            'date': rotation_date.strftime("%Y-%m-%d (Sat)"), 
            'user': cleaner_user.name
        })
        
        # Avanzar al siguiente usuario para la próxima semana
        current_cleaner_index = (current_cleaner_index + 1) % len(users)
        
    db.close()
    return schedule
    
    # BASURA
def get_task_status():
    db.connect(reuse_if_open=True)

    trash_status = {}
    try:
        trash_cat = EventCategory.get(EventCategory.name == TRASH_CATEGORY_NAME)
        last_trash = Event.select().where(Event.category == trash_cat).order_by(Event.logged_at.desc()).first()
        
        if last_trash:
            delta = datetime.now() - last_trash.logged_at
            days_ago = delta.days
            if days_ago < 1:
                icon, msg = '🟢', f"Done by {last_trash.user.name} ({int(delta.total_seconds()/3600)}h ago)"
            elif days_ago < 2:
                icon, msg = '🟡', f"Done yesterday by {last_trash.user.name}"
            else:
                icon, msg = '🔴', f"Not done for {days_ago} days!"
        else:
            icon, msg = '🔴', "Never registered."
        trash_status = {'name': 'Trash', 'icon': icon, 'msg': msg}
    except EventCategory.DoesNotExist:
        # Maneja si la categoría aún no se creó en database_example.py
        trash_status = {'name': 'Trash', 'icon': '⚪', 'msg': 'Category missing (Check database_example.py)'}
    except Exception as e:
        trash_status = {'name': 'Trash', 'icon': '⚪', 'msg': str(e)}

    # LIMPIEZA
    cleaning_status = {}
    schedule = get_cleaning_schedule(weeks=1) 
    if schedule:
        assigned = schedule[0]['user']
        # Busca si hay log de limpieza en los últimos 6 días
        last_clean = CleaningLog.select().join(User).where(User.name == assigned, CleaningLog.date >= (datetime.now() - timedelta(days=6)).date()).first()
        
        if last_clean:
            icon, msg = '✅', f"{assigned} completed turn."
        else:
            icon, msg = '⚠️', f"Pending: {assigned}'s turn."
    else:
        icon, msg = '⚪', "No rotation (Add users)."
        
    cleaning_status = {'name': 'Room Cleaning', 'icon': icon, 'msg': msg}
    db.close()
    return {'trash': trash_status, 'cleaning': cleaning_status}


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>dormmon</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        button { padding: 8px 16px; margin: 5px; cursor: pointer; }
        input, select, textarea { padding: 5px; margin: 5px; }
        .dialog { border: 1px solid #ccc; padding: 15px; margin: 10px 0; background: #f9f9f9; }
        .hidden { display: none; }
        table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h1>dormmon</h1>
    
    <div>
        <button hx-get="/dialog/add_user" hx-target="#dialogs">Add User</button>
        <button hx-get="/dialog/add_item" hx-target="#dialogs">Add Item</button>
        <button hx-get="/dialog/set_stock" hx-target="#dialogs">Set Item Stock</button>
        <button hx-get="/dialog/add_event" hx-target="#dialogs">Add Event</button>

        <!--buttons for task status and clean schedule-->
        <button hx-get="/status_view" hx-target="#dialogs" >📊 Task Status</button>
        <button hx-get="/schedule" hx-target="#dialogs">📅 Cleanning Schedule</button>
    </div>
    
    <div id="dialogs"></div>
    
    <h2>Users</h2>
    <div id="users" hx-get="/users" hx-trigger="load, userUpdated from:body">
        Loading...
    </div>
    
    <h2>Items</h2>
    <div id="items" hx-get="/items" hx-trigger="load, itemUpdated from:body">
        Loading...
    </div>
    
    <h2>Events</h2>
    <div id="events" hx-get="/events" hx-trigger="load, eventUpdated from:body">
        Loading...
    </div>
</body>
</html>
'''

# Main route or URL (the home page: http://localhost:5000/)
@app.route("/")
def index():
    #returns the html
    return render_template_string(HTML_TEMPLATE)

# User management
@app.route("/users")
def list_users():
    #Select all users from db
    users = User.select()
    #creates a html table with users
    html = "<table><tr><th>Username</th><th>Created</th></tr>"
    for user in users:
        html += f"<tr><td>{user.name}</td><td>{user.created_at}</td></tr>"
    html += "</table>"
    return html

@app.route("/dialog/add_user")
def dialog_add_user():
    return '''
    <div class="dialog">
        <h3>Add User</h3>
        <form hx-post="/users" hx-encoding="multipart/form-data" hx-target="#dialogs" hx-swap="innerHTML">
            <div>
                <label>Username:</label>
                <input type="text" name="username" required>
            </div>
            <div>
                <label>Images (multiple):</label>
                <input type="file" name="images" multiple accept="image/*" required>
            </div>
            <button type="submit">Add User</button>
            <button type="button" onclick="this.closest('.dialog').remove()">Cancel</button>
        </form>
    </div>
    '''
# Route to CREATE a user (POST)
@app.route("/users", methods=["POST"])
def create_user():
    #gets username from the from
    username = request.form.get('username')
    if not username:
        return "Error: Username required", 400
    #unique username
    if User.select().where(User.username == username).exists():
        return "Error: Username already exists", 400
    #gets the image of the user
    files = request.files.getlist('images')
    if not files or not any(f.filename for f in files):
        return "Error: At least one image required", 400
    
    # Process all images and combine encodings
    all_encodings = []
    for file in files:
        if file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                #load image with face recognition
                image = face_recognition.load_image_file(filepath)
                #detect faces and get their encodings
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    all_encodings.append(encodings[0])
                os.remove(filepath)  # Clean up
            except Exception as e:
                os.remove(filepath)  # Clean up on error
                return f"Error processing image: {str(e)}", 400
    
    if not all_encodings:
        return "Error: No faces detected in images", 400
    
    # Average all encodings to create a single encoding
    avg_encoding = np.mean(all_encodings, axis=0)
    
    # Save user to the database with encoding
    User.create(
        username=username,
        face_encoding=avg_encoding.tobytes(),
        created_at=datetime.now()
    )
    # Returns success message and triggers 'userUpdated' event to refresh the list
    return f'<div class="dialog"><p>User "{username}" added successfully!</p><button onclick="this.closest(\'.dialog\').remove(); htmx.trigger(document.body, \'userUpdated\')">Close</button></div>'

# Item management
@app.route("/items")
def list_items():
    #select all items from db
    items = Item.select()
    #create a table
    html = "<table><tr><th>Name</th><th>Icon</th><th>Stock</th><th>Created</th></tr>"
    for item in items:
        #get all stocks from the item
        stock = ItemStock.select().where(ItemStock.item == item).first()
        stock_value = stock.stock if stock else 0
        html += f"<tr><td>{item.name}</td><td>{item.icon}</td><td>{stock_value}</td><td>{item.created_at}</td></tr>"
    html += "</table>"
    return html

#Add item form
@app.route("/dialog/add_item")
def dialog_add_item():
    return '''
    <div class="dialog">
        <h3>Add Item</h3>
        <form hx-post="/items" hx-target="#dialogs" hx-swap="innerHTML">
            <div>
                <label>Name:</label>
                <input type="text" name="name" required>
            </div>
            <div>
                <label>Icon:</label>
                <input type="text" name="icon" placeholder="📦" required>
            </div>
            <button type="submit">Add Item</button>
            <button type="button" onclick="this.closest('.dialog').remove()">Cancel</button>
        </form>
    </div>
    '''

#Creation of a new item
@app.route("/items", methods=["POST"])
#function to create an item
def create_item():
    #get name and icon from the form
    name = request.form.get('name')
    icon = request.form.get('icon', '📦')
    
    if not name:
        return "Error: Name required", 400
    #create item in the db
    item = Item.create(name=name, icon=icon, created_at=datetime.now())
    #set initial stock to 0
    ItemStock.create(item=item, stock=0)
    
    return f'<div class="dialog"><p>Item "{name}" added successfully!</p><button onclick="this.closest(\'.dialog\').remove(); htmx.trigger(document.body, \'itemUpdated\')">Close</button></div>'

# Stock form
@app.route("/dialog/set_stock")
#function to create the stock form
def dialog_set_stock():
    #select all items from the db
    items = Item.select()
    #shows the items in a drop-down menu
    options = ''.join([f'<option value="{item.id}">{item.name}</option>' for item in items])
    return f'''
    <div class="dialog">
        <h3>Set Item Stock</h3>
        <form hx-post="/stock" hx-target="#dialogs" hx-swap="innerHTML">
            <div>
                <label>Item:</label>
                <select name="item_id" required>
                    {options}
                </select>
            </div>
            <div>
                <label>Stock:</label>
                <input type="number" name="stock" value="0" required>
            </div>
            <button type="submit">Set Stock</button>
            <button type="button" onclick="this.closest('.dialog').remove()">Cancel</button>
        </form>
    </div>
    '''

#url to update the stock
@app.route("/stock", methods=["POST"])
def set_stock():
    #get id of item
    item_id = request.form.get('item_id')
    #get stock number
    stock = int(request.form.get('stock', 0))
    
    try:
        #search the item by its id
        item = Item.get_by_id(item_id)
        #search or create stock
        item_stock, created = ItemStock.get_or_create(item=item, defaults={'stock': stock})
        #if already created, update the value
        if not created:
            item_stock.stock = stock
            item_stock.save()
        
        return f'<div class="dialog"><p>Stock for "{item.name}" set to {stock}!</p><button onclick="this.closest(\'.dialog\').remove(); htmx.trigger(document.body, \'itemUpdated\')">Close</button></div>'
    except Item.DoesNotExist:
        return "Error: Item not found", 400

# Event management
@app.route("/events")
def list_events():
    #get the last 50 events, ordered by descendent date
    events = Event.select().order_by(Event.logged_at.desc()).limit(50)
    #create the html table
    html = "<table><tr><th>User</th><th>Category</th><th>Cost</th><th>Stock</th><th>Notes</th><th>Logged At</th></tr>"
    for event in events:
        stock_info = f"{event.stock.item.name}: {event.stock.stock}" if event.stock else "-"
        cost_info = f"${event.cost}" if event.cost else "-"
        html += f"<tr><td>{event.user.name}</td><td>{event.category.icon} {event.category.name}</td><td>{cost_info}</td><td>{stock_info}</td><td>{event.notes}</td><td>{event.logged_at}</td></tr>"
    html += "</table>"
    return html

#add event form
@app.route("/dialog/add_event")
def dialog_add_event():
    #select all users, categories, items, templates from the db
    users = User.select()
    categories = EventCategory.select()
    items = Item.select()
    templates = EventTemplate.select()
    
    user_options = ''.join([f'<option value="{user.id}">{user.name}</option>' for user in users])
    category_options = ''.join([f'<option value="{cat.id}">{cat.icon} {cat.name}</option>' for cat in categories])
    item_options = ''.join([f'<option value="{item.id}">{item.name}</option>' for item in items])
    template_options = '<option value="">-- Select Template --</option>'
    template_options += '<option value="current">+ Add Current as Template</option>'
    template_options += ''.join([f'<option value="tpl_{tpl.id}">Template #{tpl.id} ({tpl.category.name})</option>' for tpl in templates])
    
    return f'''
    <div class="dialog">
        <h3>Add Event</h3>
        <form hx-post="/events" hx-target="#dialogs" hx-swap="innerHTML">
            <div>
                <label>User:</label>
                <select name="user_id" required>
                    {user_options}
                </select>
            </div>
            <div>
                <label>Template:</label>
                <select name="template_id" id="template_select" onchange="loadTemplate(this.value)">
                    {template_options}
                </select>
                <span id="template_actions"></span>
            </div>
            <div>
                <label>Category:</label>
                <select name="category_id" id="category_select" required>
                    {category_options}
                </select>
                <input type="text" name="new_category_name" id="new_category_name" placeholder="Or enter new category name" style="display:none;">
                <input type="text" name="new_category_icon" id="new_category_icon" placeholder="Icon" style="display:none;">
                <button type="button" onclick="toggleNewCategory()">Add New Category</button>
            </div>
            <div>
                <label>Cost:</label>
                <input type="number" step="0.01" name="cost" id="cost_input">
            </div>
            <div>
                <label>Item Stock (optional):</label>
                <select name="item_id" id="item_select">
                    <option value="">-- None --</option>
                    {item_options}
                </select>
                <input type="number" name="item_stock" id="item_stock_input" placeholder="Stock change" value="0">
            </div>
            <div>
                <label>Notes:</label>
                <textarea name="notes" id="notes_input"></textarea>
            </div>
            <div>
                <label>Photo Path:</label>
                <input type="text" name="photo_path" placeholder="Optional">
            </div>
            <button type="submit">Add Event</button>
            <button type="button" onclick="this.closest('.dialog').remove()">Cancel</button>
        </form>
        <script>
            function toggleNewCategory() {{
                const newName = document.getElementById('new_category_name');
                const newIcon = document.getElementById('new_category_icon');
                const categorySelect = document.getElementById('category_select');
                if (newName.style.display === 'none') {{
                    newName.style.display = 'inline';
                    newIcon.style.display = 'inline';
                    categorySelect.required = false;
                }} else {{
                    newName.style.display = 'none';
                    newIcon.style.display = 'none';
                    categorySelect.required = true;
                }}
            }}
            function loadTemplate(value) {{
                if (value.startsWith('tpl_')) {{
                    const templateId = value.replace('tpl_', '');
                    htmx.ajax('GET', '/template/' + templateId, {{target: '#template_data', swap: 'innerHTML'}});
                }} else {{
                    document.getElementById('template_data').innerHTML = '';
                }}
            }}
        </script>
        <div id="template_data"></div>
    </div>
    '''

@app.route("/template/<int:template_id>")
def get_template(template_id):
    try:
        template = EventTemplate.get_by_id(template_id)
        html = f'''
        <div style="margin: 10px 0; padding: 10px; background: #e8f4f8; border: 1px solid #ccc;">
            <p><strong>Template #{template_id}</strong></p>
            <p>Category: {template.category.icon} {template.category.name}</p>
            <p>Cost: ${template.cost if template.cost else "None"}</p>
            <p>Notes: {template.notes}</p>
            <button onclick="applyTemplate({template_id})">Apply Template</button>
            <button onclick="deleteTemplate({template_id})">Delete Template</button>
        </div>
        '''
        
        # Get template item stocks
        item_stocks = EventTemplateItemStock.select().where(EventTemplateItemStock.template == template)
        if item_stocks:
            html += "<p><strong>Item Stocks:</strong></p><ul>"
            for ts in item_stocks:
                html += f"<li>{ts.item.name}: {ts.stock}</li>"
            html += "</ul>"
        
        html += f'''
        <script>
            function applyTemplate(templateId) {{
                fetch('/template/' + templateId + '/apply')
                    .then(response => response.json())
                    .then(data => {{
                        document.getElementById('category_select').value = data.category_id;
                        document.getElementById('cost_input').value = data.cost || '';
                        document.getElementById('notes_input').value = data.notes || '';
                        if (data.item_id) {{
                            document.getElementById('item_select').value = data.item_id;
                            document.getElementById('item_stock_input').value = data.item_stock || 0;
                        }}
                    }})
                    .catch(error => console.error('Error:', error));
            }}
            function deleteTemplate(templateId) {{
                if (confirm('Delete this template?')) {{
                    htmx.ajax('DELETE', '/template/' + templateId, {{
                        target: '#template_data',
                        swap: 'innerHTML',
                        handler: function() {{
                            htmx.ajax('GET', '/templates/options', {{
                                target: '#template_select',
                                swap: 'innerHTML'
                            }});
                        }}
                    }});
                }}
            }}
        </script>
        '''
        return html
    except EventTemplate.DoesNotExist:
        return "Template not found", 404

@app.route("/template/<int:template_id>/apply")
def apply_template(template_id):
    try:
        template = EventTemplate.get_by_id(template_id)
        data = {
            'category_id': template.category.id,
            'cost': str(template.cost) if template.cost else None,
            'notes': template.notes
        }
        
        # Get first item stock if exists
        item_stock = EventTemplateItemStock.select().where(EventTemplateItemStock.template == template).first()
        if item_stock:
            data['item_id'] = item_stock.item.id
            data['item_stock'] = item_stock.stock
        
        return jsonify(data)
    except EventTemplate.DoesNotExist:
        return jsonify({'error': 'Template not found'}), 404

@app.route("/templates/options")
def templates_options():
    templates = EventTemplate.select()
    options = '<option value="">-- Select Template --</option>'
    options += '<option value="current">+ Add Current as Template</option>'
    options += ''.join([f'<option value="tpl_{tpl.id}">Template #{tpl.id} ({tpl.category.name})</option>' for tpl in templates])
    return options

@app.route("/template/<int:template_id>", methods=["DELETE"])
def delete_template(template_id):
    try:
        template = EventTemplate.get_by_id(template_id)
        template.delete_instance()
        return '<p>Template deleted successfully!</p>'
    except EventTemplate.DoesNotExist:
        return "Template not found", 404

#url to create the event
@app.route("/events", methods=["POST"])
def create_event():
    #get all the data that the user loaded to the form
    user_id = request.form.get('user_id')
    category_id = request.form.get('category_id')
    new_category_name = request.form.get('new_category_name')
    new_category_icon = request.form.get('new_category_icon', '📋')
    cost = request.form.get('cost')
    item_id = request.form.get('item_id')
    item_stock = request.form.get('item_stock')
    notes = request.form.get('notes', '')
    photo_path = request.form.get('photo_path', '')
    template_id = request.form.get('template_id')
    
    try:
        #get the user
        user = User.get_by_id(user_id)
        
        # Handle category
        if new_category_name:
            #if there's a new category name, create it
            category = EventCategory.create(
                name=new_category_name,
                icon=new_category_icon,
                created_at=datetime.now()
            )
        else:
            #if there's no new category, get the existent one
            category = EventCategory.get_by_id(category_id)
        
        # Handle cost
        cost_decimal = Decimal(cost) if cost else None
        
        # Handle item stock
        stock_obj = None
        #if theres an item and stock
        if item_id and item_stock:
            #get the item
            item = Item.get_by_id(item_id)
            #we get or create the stock
            item_stock_obj, _ = ItemStock.get_or_create(item=item, defaults={'stock': 0})
            #add to the current stock
            item_stock_obj.stock += int(item_stock)
            #save the new stock
            item_stock_obj.save()
            #save the current stock in a new variable
            stock_obj = item_stock_obj
        
        # Create event
        Event.create(
            user=user,
            category=category,
            cost=cost_decimal,
            stock=stock_obj,
            notes=notes,
            photo_path=photo_path,
            logged_at=datetime.now(),
            modified_at=datetime.now()
        )
        
        # Handle template creation if requested
        if template_id == 'current':
            template = EventTemplate.create(
                category=category,
                cost=cost_decimal,
                notes=notes
            )
            
            # Add item stock to template if exists
            if stock_obj and item_stock:
                EventTemplateItemStock.create(
                    template=template,
                    item=stock_obj.item,
                    stock=int(item_stock)
                )
        
        return f'<div class="dialog"><p>Event added successfully!</p><button onclick="this.closest(\'.dialog\').remove(); htmx.trigger(document.body, \'eventUpdated\')">Close</button></div>'
    except Exception as e:
        return f"Error: {str(e)}", 400



#-----PARTE DE JAZ-----------
#cleaning schedule 
@app.route("/schedule")
def show_schedule():
    """Muestra la tabla del calendario de limpieza semanal."""
    schedule = get_cleaning_schedule(weeks=6)
    
    html = "<h2>🧹 Weekly Cleaning Schedule</h2>"
    
    if not schedule: return html + "<p>Add users to start rotation.</p>"
    
    html += "<table><tr><th>Date</th><th>Assigned User</th></tr>"
    for entry in schedule: html += f"<tr><td>{entry['date']}</td><td><strong>{entry['user']}</strong></td></tr>"
    
    return html + "</table><p style='color:#666;'>Rotation advances every Saturday</p>"

#task status

@app.route("/status_view")
def status_view():
    """Vista de Estado de Tareas (Semáforos)."""
    status = get_task_status()
    s_clean = status['cleaning']
    s_trash = status['trash']
    html = "" 
    html += "<h2>📊 Current Task Status</h2>"
    
    # Tarjetas de estado
    html += f'''
    <div class="dialog">
        <div >
            <div>{s_clean['icon']}</div>
            <div><strong>{s_clean['name']}</strong><br>{s_clean['msg']}</div>
        </div>
        <div style="border:none;">
            <div >{s_trash['icon']}</div>
            <div><strong>{s_trash['name']}</strong><br>{s_trash['msg']}</div>
        </div>
    </div>
    '''
    
    html += '</div>'
    return html

if __name__ == "__main__":
    app.run(debug=True)
