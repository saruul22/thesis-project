from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from .models import Weapon
import segno
from io import BytesIO

def weapon_qr_code(request, weapon_id):
    weapon = get_object_or_404(Weapon, id=weapon_id)
    qr = weapon.get_qr_code()

    if qr:
        out = BytesIO()
        qr.save(out, kind='png', scale=10)
        response = HttpResponse(out.getvalue(), content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="weapon_{weapon.serial_number}_qr.png"'
        return response
    
    return HttpResponse("QR Code not available", status=404)

# Create your views here.
