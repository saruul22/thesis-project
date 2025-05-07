from django.shortcuts import render
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
import json
import time
from inventory.models import Personnel, Weapon
from face_authentication.models import WeaponTransaction, FaceRecord
from .export import export_transactions_csv, export_transactions_excel, export_transactions_pdf

def index(request):
    """Main dashboard view"""
    return render(request, 'dashboard/index.html')

def personnel_count(request):
    """Widget for personnel count"""
    count = Personnel.objects.count()
    active_count = Personnel.objects.filter(active_status=True).count()
    
    return render(request, 'dashboard/widgets/personnel_count.html', {
        'count': count,
        'active_count': active_count
    })

def weapons_count(request):
    """Widget for weapons count"""
    count = Weapon.objects.count()
    available_count = Weapon.objects.filter(status='available').count()
    assigned_count = Weapon.objects.filter(status='assigned').count()
    
    # Count based on location (if field exists)
    field_count = Weapon.objects.filter(location='out').count()
    armory_count = Weapon.objects.filter(location='in').count()
    
    return render(request, 'dashboard/widgets/weapons_count.html', {
        'count': count,
        'available_count': available_count,
        'assigned_count': assigned_count,
        'field_count': field_count,
        'armory_count': armory_count
    })

def face_records_count(request):
    """Widget for face records count"""
    count = FaceRecord.objects.count()
    active_count = FaceRecord.objects.filter(is_active=True).count()
    
    return render(request, 'dashboard/widgets/face_records_count.html', {
        'count': count,
        'active_count': active_count
    })

def transaction_logs(request):
    """Widget for transaction logs"""
    transactions = WeaponTransaction.objects.select_related('weapon', 'personnel').order_by('-timestamp')

    # Apply date filters if provided
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date:
        transactions = transactions.filter(timestamp__date__gte=start_date)

    if end_date:
        transactions = transactions.filter(timestamp__date__lte=end_date)

    # Paginate if needed
    transactions = transactions[:20]
    
    return render(request, 'dashboard/widgets/transaction_logs.html', {
        'transactions': transactions,
        'start_date': start_date,
        'end_date': end_date
    })

def transaction_sse(request):
    """Server-Sent Events endpoint for real-time transaction updates"""
    def event_stream():
        last_transaction_id = request.GET.get('last_id')
        
        while True:
            # Check for new transactions
            latest_transaction = WeaponTransaction.objects.order_by('-timestamp').first()
            
            if latest_transaction and (not last_transaction_id or str(latest_transaction.id) != last_transaction_id):
                # New transaction found, send event
                last_transaction_id = str(latest_transaction.id)
                
                data = {
                    'id': last_transaction_id,
                    'weapon': f"{latest_transaction.weapon.weapon_model} - {latest_transaction.weapon.serial_number}",
                    'personnel': f"{latest_transaction.personnel.rank} {latest_transaction.personnel.first_name} {latest_transaction.personnel.last_name}",
                    'transaction_type': latest_transaction.transaction_type,
                    'timestamp': latest_transaction.timestamp.isoformat()
                }
                
                yield f"event: new-transaction\ndata: {json.dumps(data)}\n\n"
            
            time.sleep(2)  # Check every 2 seconds
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable buffering for Nginx
    return response

def reports(request):
    # Transaction report page filtertei bas exporttoi hamt
    transactions = WeaponTransaction.objects.select_related('weapon', 'personnel').order_by('-timestamp')

    # Filteree oruulna
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    transaction_type = request.GET.get('transaction_type')

    if start_date:
        transactions = transactions.filter(timestamp__date__gte=start_date)

    if end_date:
        transactions = transactions.filter(timestamp__date__lte=end_date)

    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)

    transaction_count = transactions.count()

    return render(request, 'dashboard/reports.html', {
        'transactions': transactions,
        'transaction_count': transaction_count,
        'start_date': start_date,
        'end_date': end_date,
        'transaction_type': transaction_type
    })

def weapon_status_chart(request):
    # Get counts for different weapon statuses
    total_weapons = Weapon.objects.count()
    available_count = Weapon.objects.filter(status='available').count()
    assigned_count = Weapon.objects.filter(status='assigned').count()
    maintenance_count = Weapon.objects.filter(status='maintenance').count()
    decommissioned_count = Weapon.objects.filter(status='decommissioned').count()

    # Get counts for weapon locations
    in_armory = Weapon.objects.filter(location='in').count()
    in_field = Weapon.objects.filter(location='out').count()

    # Prepare data for the charts
    status_data = {
        'labels': ['Бэлэн байгаа', 'Хуваарилагдсан', 'Засварт', 'Актлагдсан'],
        'datasets': [{
            'data': [available_count, assigned_count, maintenance_count, decommissioned_count],
            'backgroundColor': ['#10B981', '#3B82F6', '#F59E0B', '#EF4444']
        }]
    }

    location_data = {
        'labels': ['Хадгалагдсан', 'Гарсан'],
        'datasets': [{
            'data': [in_armory, in_field],
            'backgroundColor': ['#6366F1', '#F97316']
        }]
    }

    return JsonResponse({
        'status_data': status_data,
        'location_data': location_data
    })

def weapon_charts(request):
    return render(request, 'dashboard/weapon_charts.html')

# dashboard/views.py (add this)
def chart_refresher(request):
    """Widget for auto-refreshing chart data"""
    return render(request, 'dashboard/widgets/chart_data_refresher.html')
