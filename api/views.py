from django.shortcuts import render, get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.pagination import CursorPagination
from django.contrib.auth import authenticate
from api.passwordAuth import MultiDBJWTAuthentication
from .serializers import *
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.timezone import now
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from django.conf import settings
from django.utils import timezone
#from django.contrib.gis.geoip2 import GeoIP2
import logging
#import pytesseract
from django.http import JsonResponse
import requests
from datetime import date,datetime
from django.forms.models import model_to_dict
from collections import defaultdict
import json
import time
from django.db import connections
from django.db.models import Q, Sum, Max
#pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
logger = logging.getLogger(__name__)
def get_db_alias(request):
    return 'tsl_db' if request.path.startswith('/tsl/') else 'default'
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        db_alias = 'tsl_db' if request.path.startswith('/tsl/') else 'default'
        serializer = LoginSerializer(data=request.data, db_alias=db_alias)
        if not serializer.is_valid():
            print(serializer.errors)  
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        access_token['username'] = user.user_code
        access_token['user_id'] = user.user_id

        return Response({
            'access': str(access_token),
            'refresh': str(refresh),
            'user': {
                'username': user.user_code,
                'user_id': user.user_id,
            }
        }, status=status.HTTP_200_OK)

    
class ProfileView(APIView):
    authentication_classes = [MultiDBJWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        user = request.user
        db_alias = get_db_alias(request)
        fresh_user = User.objects.using(db_alias).get(pk=user.pk)
        serializer = UserSerializer(fresh_user)
        return Response(serializer.data)
    
class TripListView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        db_alias = get_db_alias(request)
        
        trips = TripTicketModel.objects.using(db_alias).all().order_by('-trip_ticket_id').values().filter(is_final_trip=1)
        drivers = TripDriverModel.objects.using(db_alias).all()

        driver_mapping = {driver.entity_id: driver.entity_name for driver in drivers}
        
        trip_serializer = TripTicketSerializer(trips, many=True)
        print(f"Current DB: {connection.alias}")
        for trip in trip_serializer.data:
            trip['entity_name'] = driver_mapping.get(trip['entity_id'], '')
            trip['asst_entity_name'] = driver_mapping.get(trip['asst_entity_id'], '')
            trip['dispatcher'] = driver_mapping.get(trip['dispatched_by'], '')

        return Response({'triplist': trip_serializer.data})

class TripBranchView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        db_alias = get_db_alias(request)
        
        trip_ticket_id = request.query_params.get('id')
        if not trip_ticket_id:  
            return Response({"error": "ID is required."}, status=400)
        
        try:
           
                
            tripdetail_data = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id)
            
            if not tripdetail_data.exists():
                return Response({"error": "Trip ticket not found."}, status=404)
        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)
        
        tripdetail_serializer = TripDetailsSerializer(tripdetail_data, many=True)
        tripdetails = tripdetail_serializer.data

        branch_ids = list(set([detail['branch_id'] for detail in tripdetails])) #convert to list and remove duplicates of branch id

        branch_data = TripBranchModel.objects.using(db_alias).order_by('branch_name').filter(branch_id__in=branch_ids) # match
        branch_serializer = TripBranchSerializer(branch_data, many=True)


        response_data = [ 
            { 
            'branch_id': branch['branch_id'], 
            'branch_name': branch['branch_name'] 
            } 
            for branch in branch_serializer.data 
        ]
        return Response(response_data)


class TripDetailView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        db_alias = get_db_alias(request)
        
        trip_ticket_id = request.query_params.get('trip_ticket_id')
        branch_id = request.query_params.get('branch_id')

        if not trip_ticket_id:
            return Response({"error": "trip_ticket_id is required."}, status=400)
#, cast(null as nvarchar(30)) as remarks
        try:
            connection = connections[db_alias]
            with connection.cursor() as cursor:
                cursor.execute("""
                      SELECT 
                        td.*,
                        cast(null as bigint) as item_id,   cast(null as nvarchar(30)) as item_description,   cast(null as nvarchar(30)) as barcode,   cast(null as int) as uom_id,
                        cast(null as nvarchar(30)) as uom_code,  cast(null as int) as item_qty
                    FROM scm_tr_trip_ticket_detail td
                    WHERE td.trip_ticket_id = %s AND td.branch_id = %s order by td.ref_trans_no asc
                """, [trip_ticket_id, branch_id])
                
                columns = [col[0] for col in cursor.description]
                raw_data = [dict(zip(columns, row)) for row in cursor.fetchall()]

            if not raw_data:
                return Response({"error": "Trip ticket not found."}, status=404)

            trips_map = {}
            branches = set()
            
            for row in raw_data:
                trip_id = row['trip_ticket_detail_id']
                
                if trip_id not in trips_map:
                    trips_map[trip_id] = {
                        'trip_ticket_detail_id': trip_id,
                        'trip_ticket_id': row['trip_ticket_id'],
                        'branch_id': row['branch_id'],
                        'ref_trans_id': row['ref_trans_id'],
                        'ref_trans_no': row['ref_trans_no'],
                        'ref_trans_date': row['ref_trans_date'],
                        'trans_name': row['trans_name'],
                        'detail_volume': row['detail_volume'],
                        'remarks': row['remarks'],
                        'items': [],
                        'branch_name': row.get('branch_name'),
                        'is_posted': row['is_posted'],
                        'updated_date':row['updated_date'],
                        'created_date':row['created_date'],
                    }
                    branches.add(row['branch_id'])
                
                # Only add unique items per trip
                existing_items = {i['item_id'] for i in trips_map[trip_id]['items']}
                if row['item_id'] not in existing_items:
                    trips_map[trip_id]['items'].append({
                        'item_id': row['item_id'],
                        'item_qty': str(row['item_qty']),
                        'remarks': row['remarks'],
                        'item_description': row['item_description'],
                        'barcode': row['barcode'],
                        'uom_id': row['uom_id'],
                        'uom_code': row['uom_code'],
                       
                    })
            #logger.warning("tete", list(trips_map.values()))
            # Get branch details
            branch_data = TripBranchModel.objects.using(db_alias).filter(
                branch_id__in=branches
            )
            branch_serializer = TripBranchSerializer(branch_data, many=True)
            return Response({
                'tripdetails': list(trips_map.values()),
                'branches': branch_serializer.data
            })

        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)
class ManageAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        db_alias = get_db_alias(request)
        
        user_logs = TripTicketBranchLogsModel.objects.using(db_alias).order_by('-log_id').filter(created_by=user.user_id)
      
        trip_ticket_ids = user_logs.values_list('trip_ticket_id', flat=True).distinct()
        branch_ids = user_logs.values_list('branch_id', flat=True).distinct()       
        trip_tickets = TripTicketModel.objects.using(db_alias).filter(
            trip_ticket_id__in=trip_ticket_ids
        )
        trip_details = TripDetailsModel.objects.using(db_alias).filter(branch_id__in= branch_ids)
        ticket_number_map = {
            ticket.trip_ticket_id: ticket.trip_ticket_no
            for ticket in trip_tickets
        }
        trip_detail_map = {
            detail.branch_id:detail.branch_name
            for detail in trip_details
        }
        userlogs_serializer = BranchLogsSerializer(user_logs, many=True)

        response_data = []
        for log_data in userlogs_serializer.data:
            log_data['trip_ticket_no'] = ticket_number_map.get(log_data['trip_ticket_id'], '')
            log_data['branch_name'] = trip_detail_map.get(log_data['branch_id'], '')
            response_data.append(log_data)

        return Response({'userlogs': response_data})
    
class ManageTripDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.auth['user_id']
        db_alias = get_db_alias(request)

        user_trips_qs = OutslipImagesModel.objects.using(db_alias).filter(created_by=user_id).values('trip_ticket_id', 'trip_ticket_detail_id', 'created_date')

        if not user_trips_qs.exists():
            return Response({"tripdetails": []}, status=status.HTTP_200_OK)
        image_dates = {
            (trip['trip_ticket_id'], trip['trip_ticket_detail_id']): trip['created_date']
            for trip in user_trips_qs
        }
        trip_ids = {trip['trip_ticket_id'] for trip in user_trips_qs}
        trip_detail_ids = {trip['trip_ticket_detail_id'] for trip in user_trips_qs}
        #trip_ids = user_trips_qs.values_list('trip_ticket_id', flat=True).distinct()
        #trip_detail_ids = user_trips_qs.values_list('trip_ticket_detail_id', flat=True).distinct()
        logger.warning(f"tite {trip_ids}")
        if db_alias == 'default':

            trip_details_qs = TripDetailsModel.objects.using(db_alias).order_by('branch_name', 'ref_trans_no').filter(
                trip_ticket_id__in=trip_ids,
                trip_ticket_detail_id__in=trip_detail_ids
            )
        else:
            trip_details_qs = TripDetailsModel.objects.using(db_alias).order_by('entity_name', 'ref_trans_no').filter(
                trip_ticket_id__in=trip_ids,
                trip_ticket_detail_id__in=trip_detail_ids
            )
        trip_tickets_map = {
            t.trip_ticket_id: {
                "trip_ticket_no": t.trip_ticket_no,
                "trip_ticket_date": t.trip_ticket_date
            }
            for t in TripTicketModel.objects.using(db_alias)
                .filter(trip_ticket_id__in=trip_ids)
                .only("trip_ticket_id", "trip_ticket_no", "trip_ticket_date")
        }

        grouped_trips = {}
        for trip in trip_details_qs:
            tid = trip.trip_ticket_id
            detail_id = trip.trip_ticket_detail_id
            if tid not in grouped_trips:
                grouped_trips[tid] = {
                    "trip_ticket_id": tid,
                    "trip_ticket_no": trip_tickets_map.get(tid, {}).get("trip_ticket_no", ""),
                    "trip_ticket_date": trip_tickets_map.get(tid, {}).get("trip_ticket_date", ""),
                    "trip_ticket_detail_id": []
                }
            created_date = image_dates.get((tid, detail_id))
            grouped_trips[tid]["trip_ticket_detail_id"].append({
                "trip_ticket_detail_id": trip.trip_ticket_detail_id,
                "trip_ticket_id": tid,
                "trans_name": trip.trans_name,
                "branch_name": trip.branch_name if db_alias != 'tsl_db' else trip.entity_name,
                "ref_trans_date": trip.ref_trans_date,
                "ref_trans_id": trip.ref_trans_id,
                "ref_trans_no": trip.ref_trans_no,
                "created_date": created_date,
            })

        return Response({"tripdetails": list(grouped_trips.values())})
    
class EditUploadedPictures(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        upload_images = request.FILES.getlist('image', [])
        upload_remarks = request.data.getlist('upload_remarks', [])
        trip_ticket_detail_id = request.data.get('trip_ticket_detail_id')
        trip_ticket_id = request.data.get('trip_ticket_id')
        branch_id = request.data.get('branch_id')
        branch_name = request.data.get('branch_name')
        trans_name = request.data.get('trans_name')
        username = request.data.get('username')
        ref_trans_no = request.data.get('ref_trans_no')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        user_id = request.user.user_id
        db_alias = get_db_alias(request)
        connection = connections[db_alias]
        base_url = connection.settings_dict.get('BASE_URL', settings.BASE_URL)
        #logger.warning(f"upload_images: {upload_images}")
        #logger.warning(f"upload_remarks: {upload_remarks}")

        try:
            # Get clock-in data once
            has_clock_in = TripTicketBranchLogsModel.objects.using(db_alias).filter(
                created_by=user_id,
                trip_ticket_id=trip_ticket_id,
                branch_id=branch_id,
                time_in__isnull=False,
            ).first()

            trip_ticket_no = TripTicketModel.objects.using(db_alias).filter(
                trip_ticket_id=trip_ticket_id
            ).values_list('trip_ticket_no', flat=True).first() if has_clock_in else None

            uploaded_files = []
            errors = []

            for i, upload_image in enumerate(upload_images):
                try:
                    remark = upload_remarks[i] if i < len(upload_remarks) else ''
                    
                    # Process image
                    with Image.open(upload_image) as img:
                        img_format = img.format or 'JPEG'
                        
                        # Apply watermark if clocked in
                        if has_clock_in:
                            location_data = reverse_geocode(latitude, longitude)
                            location_in = location_data.get('display_name', 'Unknown location')
                            
                            watermark_text = (
                                f"Trip Ticket No: {trip_ticket_no}\n"
                                f"Branch Name: {branch_name}\n"
                                f"Transaction Name: {trans_name}\n"
                                f"Trans No: {ref_trans_no}\n"
                                f"Taken by: {username}\n"
                                f"Date Taken: {timezone.now()}\n"
                                f"Edited Address: {location_in}\n"
                            )
                            
                            draw = ImageDraw.Draw(img)
                            font = ImageFont.load_default(size=64)
                            draw.multiline_text((20, 20), watermark_text, fill="white", font=font)
                        
                        # Prepare image for saving
                        img_io = BytesIO()
                        img.save(img_io, format=img_format, quality=95)
                        img_io.seek(0)
                        
                        if db_alias == 'tsl_db':
                            file_name = f'tsloutslips/{upload_image.name}'
                        
                        else:
                            file_name = f'outslips/{upload_image.name}'
                        saved_path = default_storage.save(file_name, ContentFile(img_io.read()))
                        file_url = f"{base_url}{settings.MEDIA_URL}{saved_path}"
                        
                        # Create database record
                    OutslipImagesModel.objects.using(db_alias).create(
                        trip_ticket_detail_id=trip_ticket_detail_id,
                        trip_ticket_id=trip_ticket_id,
                        branch_id=branch_id,
                        upload_files=file_url,
                        upload_remarks=remark,
                        upload_text='Not original picture',
                        created_by=user_id,
                        updated_by=user_id,
                        created_date=timezone.now(),
                        updated_date=timezone.now()
                    )
                    
                    uploaded_files.append(file_url)
                
                except Exception as e:
                    #logger.error(f"Error processing image {upload_image.name}: {str(e)}")
                    errors.append({
                        'image': upload_image.name,
                        'error': str(e)
                    })

            if errors:
                return Response({
                    'message': 'Some images failed to upload',
                    'successful_uploads': uploaded_files,
                    'errors': errors
                }, status=status.HTTP_207_MULTI_STATUS)
                
            return Response({
                'message': 'All images uploaded successfully',
                'uploaded_files': uploaded_files
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            #logger.error(f"Unexpected error in image upload: {str(e)}")
            return Response({
                'error': 'Failed to process upload',
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
class ManageUploadedPictures(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        db_alias = get_db_alias(request)
        
        trip_ticket_detail_id = request.query_params.get('id')
        user_id = request.user.user_id
        if trip_ticket_detail_id:
            try:
                upload_data = OutslipImagesModel.objects.using(db_alias).filter(trip_ticket_detail_id=trip_ticket_detail_id, created_by = user.user_id)
                if not upload_data.exists():
                    return Response({"error": "Trip ticket Detail not found."}, status=404)

                receiving_data = TripTicketDetailReceivingModel.objects.using(db_alias).filter(
                    trip_ticket_detail_id=trip_ticket_detail_id,
                    created_by=user_id
                ).values(
                    'item_id',
                    'item_qty',
                    'serbat_id',
                    'ser_bat_no',
                    'ref_trans_detail_id'
                )

                receiving_qty_map = {
                    f"{item['item_id']}:{item['serbat_id']}:{item['ref_trans_detail_id']}": {
                    'received_qty': item['item_qty'],
                    'ser_bat_no': item.get('ser_bat_no')
                    }

                    for item in receiving_data

                }
                #logger.warning(f"f(zqw) {receiving_qty_map}")
                #logger.warning(f"f(zq2) {receiving_data}")
            except ValueError:
                return Response ({"error": "Invalid Format"}, status=404)
        try:
            connection = connections[db_alias]
            
            with connection.cursor() as cursor:
                cursor.execute("EXEC sp_mb_get_trip_item_details @trip_detail_id=%s", [trip_ticket_detail_id])   
    
                columns = [col[0] for col in cursor.description]
                raw_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if not raw_data:
                return Response({"error": "Trip ticket not found."}, status=404)
            
            trips_map = {}
            branches = set()


            for row in raw_data:
                trip_id = row['trip_ticket_detail_id']
                
                if trip_id not in trips_map:
                    trips_map[trip_id] = {
                        'trip_ticket_detail_id': trip_id,
                        'trip_ticket_id': row['trip_ticket_id'],
                        'branch_id': row['branch_id'],
                        'ref_trans_id': row['ref_trans_id'],
                        'ref_trans_no': row['ref_trans_no'],
                        'ref_trans_code_id': row['ref_trans_code_id'],
                        'ref_trans_date': row['ref_trans_date'],
                        'trans_name': row['trans_name'],
                        'remarks': row['remarks'],
                        'items': [],
                        'branch_name': row.get('branch_name'),
                        'entity_id': row['entity_id'],
                        'entity_name': row['entity_name'],
                }
                branches.add(row['branch_id'])
                connection = connections[db_alias]
                
                #existing_items = {i['item_id'] for i in trips_map[trip_id]['items']}
                #if row['item_id'] not in existing_items:
                serial_details = []
                #logger.warning(f"f(zc) {row.get('ref_trans_detail_id')} {row.get('ref_trans_detail_pkg_id')}")
                with connection.cursor() as serial_cursor:
                    serial_cursor.execute(
                        "EXEC sp_mb_get_trip_item_serial_details @trip_detail_id=%s, @ref_detail_id=%s, @ref_detail_pkg_id=%s", [trip_ticket_detail_id, row['ref_trans_detail_id'], row['ref_trans_detail_pkg_id']]
                    )
                    serial_columns = [col[0] for col in serial_cursor.description]
                    serial_data = [dict(zip(serial_columns, s_row)) for s_row in serial_cursor.fetchall()]
                    
                    for serial in serial_data:
                        key = f"{row['item_id']}:{serial.get('serbat_id', 'None')}:{row['ref_trans_detail_id']}"
                        if key in receiving_qty_map:
                            serial['received_qty'] = receiving_qty_map[key]['received_qty']
                    serial_details = serial_data
                    item_data = {
                        'item_id': row['item_id'],
                        'item_qty': str(row['item_qty']),
                        'received_qty': str(sum(
                            float(s['received_qty']) for s in serial_details
                            if 'received_qty' in s
                        )),
                        'remarks': row['remarks'],
                        'item_description': row['item_description'],
                        'barcode': row['barcode'],
                        'uom_id': row['uom_id'],
                        'uom_code': row['uom_code'],
                        'ref_trans_detail_id': row.get('ref_trans_detail_id'),
                        'ref_trans_detail_pkg_id': row.get('ref_trans_detail_pkg_id'),
                        'i_trans_no': row['i_trans_no'],
                        'main_item': row.get('main_item'),
                        'component_item': row.get('component_item'),
                        'serial_details': serial_details
                    }
                    trips_map[trip_id]['items'].append(item_data)
            branch_data = TripBranchModel.objects.using(db_alias).filter(branch_id__in=branches) # match
            branch_serializer = TripBranchSerializer(branch_data, many=True)
            upload_data_serializer = OutslipImagesSerializer(upload_data, many=True)
            uploadDetails = upload_data_serializer.data
            return Response({
                'upload_data':uploadDetails,
                'trip_details': list(trips_map.values()),
                'branches': branch_serializer.data,
                'receiving_quantities': receiving_qty_map
            })
        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)

class OutslipDetailView(APIView):
    permission_classes = [IsAuthenticated]

    
    def get(self, request):
        db_alias = get_db_alias(request)
        connection = connections[db_alias]
        
        trip_ticket_detail_id = request.query_params.get('trip_ticket_detail_id')  
        if not trip_ticket_detail_id:
            return Response({'error': 'Trip Ticket Detail ID is required. '}, status=400)
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("EXEC sp_mb_get_trip_item_details @trip_detail_id=%s", [trip_ticket_detail_id])  
    
                columns = [col[0] for col in cursor.description]
                raw_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if not raw_data:
                return Response({"error": "Trip ticket not found."}, status=404)
            
            trips_map = {}
            branches = set()

            for row in raw_data:
                trip_id = row['trip_ticket_detail_id']

                if trip_id not in trips_map:
                    trips_map[trip_id] = {
                        'trip_ticket_detail_id': trip_id,
                        'trip_ticket_id': row['trip_ticket_id'],
                        'branch_id': row['branch_id'],
                        'ref_trans_id': row['ref_trans_id'],
                        'ref_trans_no': row['ref_trans_no'],
                        'ref_trans_code_id': row['ref_trans_code_id'],
                        'ref_trans_date': row['ref_trans_date'],
                        'trans_name': row['trans_name'],
                        'remarks': row['remarks'],
                        'items': [],
                        'branch_name': row.get('branch_name'),
                        'entity_id': row['entity_id'],
                        'entity_name': row['entity_name'],
                }
                branches.add(row['branch_id'])
                
               # existing_items = {i['item_id'] for i in trips_map[trip_id]['items']}
               # if row['item_id'] not in existing_items:
                serial_details = []
                connection = connections[db_alias]
                
                #logger.warning(f"f(zc) {row.get('ref_trans_detail_id')} {row.get('ref_trans_detail_pkg_id')}")
                with connection.cursor() as serial_cursor:
                    serial_cursor.execute(
                        "EXEC sp_mb_get_trip_item_serial_details @trip_detail_id=%s, @ref_detail_id=%s, @ref_detail_pkg_id=%s", [trip_ticket_detail_id, row['ref_trans_detail_id'], row['ref_trans_detail_pkg_id']]
                    )
                    serial_columns = [col[0] for col in serial_cursor.description]
                    serial_data = [dict(zip(serial_columns, s_row)) for s_row in serial_cursor.fetchall()]
                    serial_details = serial_data
                trips_map[trip_id]['items'].append({
                    'item_id': row['item_id'],
                    'item_qty': str(row['item_qty']),
                    'remarks': row['remarks'],
                    'item_description': row['item_description'],
                    'barcode': row ['barcode'],
                    'uom_id': row['uom_id'],
                    'uom_code': row['uom_code'],
                    'ref_trans_detail_id': row.get('ref_trans_detail_id'),
                    'ref_trans_detail_pkg_id': row.get('ref_trans_detail_pkg_id'),
                    'i_trans_no': row['i_trans_no'],
                    'main_item': row.get('main_item'),
                    'component_item': row.get('component_item'),
                    'serial_details': serial_details
                })
                #logger.warning("tete", list(trips_map.values()))
            branch_data = TripBranchModel.objects.using(db_alias).filter(branch_id__in=branches) # match
            branch_serializer = TripBranchSerializer(branch_data, many=True)
            return Response({
                'tripdetails': list(trips_map.values()),
                'branches': branch_serializer.data
            })

        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)


class UploadOutslipView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        request.user
        upload_images = request.FILES.getlist('image',)    #should be same name from frointend
        upload_remarks = request.data.getlist('upload_remarks', '')
        upload_text = request.data.getlist('upload_text', '')
        trip_ticket_id = request.data.get('trip_ticket_id')
        trip_ticket_detail_id = request.data.get('trip_ticket_detail_id')
        user_id = request.data.get('created_by')
        branch_id = request.data.get('branch_id')
        branch_name = request.data.get('branch_name')
        ref_trans_no = request.data.get('ref_trans_no')
        trans_name = request.data.get('trans_name')
        username = request.data.get('username')
        db_alias = get_db_alias(request)
        connection = connections[db_alias]
        logger.warning("concon", connection)
        base_url = connection.settings_dict.get('BASE_URL', settings.BASE_URL)
        logger.warning("123", base_url)
        no_clock_in = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by=user_id,
            time_in__isnull=False,
            branch_id=branch_id,
            trip_ticket_id=trip_ticket_id,
        ).first()
       # has_clock_out = TripTicketBranchLogsModel.objects.using(db_alias).filter(
        #    created_by=user_id,
         #   trip_ticket_id=trip_ticket_id,
          #  branch_id=branch_id,
           # time_in__isnull=False,
           # time_out__isnull=False,
        #).first()
        has_clock_in = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by=user_id,
            trip_ticket_id=trip_ticket_id,
            branch_id=branch_id,
            time_in__isnull=False,
        ).first()
       # has_upload = OutslipImagesModel.objects.filter(
        #    trip_ticket_detail_id = trip_ticket_detail_id,
         #   branch_id = branch_id,
          #  created_by=user_id,
        #).first()
        trip_ticket_no = TripTicketModel.objects.using(db_alias).filter(
            trip_ticket_id=has_clock_in.trip_ticket_id).values_list('trip_ticket_no', flat=True).first()
        
        trip_details = TripDetailsModel.objects.using(db_alias).filter(
            trip_ticket_detail_id = trip_ticket_detail_id,
        ).first()
       # if has_upload:
        #    return Response(
         #       {f"You have already uploaded an outslip, you can't upload anymore. Please check your profile to view your uploaded outslips."},
          #      status=status.HTTP_400_BAD_REQUEST
          #  )
        if db_alias == 'tsl_db':
            received_by = request.data.get('received_by')
            is_delivered_str = request.data.get('is_delivered')
            is_delivered = is_delivered_str.lower() == 'true' if isinstance(is_delivered_str, str) else bool(is_delivered_str)
        

        #if has_clock_out:
         #   return Response(
          #      {"Error": f"You have already clocked out, you can't upload or edit anymore"},
           #     status=status.HTTP_400_BAD_REQUEST
            #    )
        if not no_clock_in:
            return Response(
                {"error": f"You haven't clocked in for this branch"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not upload_images:
            return Response({'error': 'Image is required'}, status=status.HTTP_402_BAD_REQUEST)
        uploaded_files = []
        errors = []
        for i, upload_image in enumerate(upload_images): #pambukod if wala, magiging json yung data sa db
        
            remark = upload_remarks[i] if i < len(upload_remarks) else None
            upload_txt = upload_text[i] if i < len(upload_text) else None
            data = request.data.copy()
            data['upload_remarks'] = remark
            data['upload_text'] = upload_txt
            serializer = OutslipImagesSerializer(data=data)
            if serializer.is_valid():
                try:
                    with Image.open(upload_image) as img:

                        if has_clock_in:
                            location_data = {
                            'latitude_in': has_clock_in.latitude_in,
                            'longitude_in': has_clock_in.longitude_in,
                            'location_in': has_clock_in.location_in,
                            'created_by': has_clock_in.created_by,
                            'created_date': has_clock_in.created_date,
                            }
                            #logger.warning(f"Raw location data: {location_data}")
                            coords = f"{has_clock_in.latitude_in},{has_clock_in.longitude_in}"
                            address = has_clock_in.location_in
                            watermarkedtext = f"Trip Ticket No:{trip_ticket_no}\nBranch Name: {branch_name}\nTransacstion Name: {trans_name}\nTrans No: {ref_trans_no}\nTaken by: {username}\nDate Taken: {timezone.now()}\nAddress: {has_clock_in.location_in}\nRemarks: {upload_remarks}"
                            #logger.warning(f"Raw location data:{has_clock_in.created_by} {coords} {address}")
                            draw = ImageDraw.Draw(img)
                            font = ImageFont.load_default(size=64)
                            text_position = (20, 20)
                            draw.multiline_text(text_position, watermarkedtext, fill="white", font=font)
                            img_io = BytesIO()
                            img.save(img_io, format='JPEG', quality=95)
                            img_io.seek(0)
                        if db_alias == 'tsl_db':
                            file_path = f'tsloutslips/{upload_image.name}'
                           
                        else:
                            file_path = f'outslips/{upload_image.name}'
                        
                        saved_path = default_storage.save(file_path, ContentFile(img_io.read()))
                        #base_url = settings.BASE_URL
                        file_url = f"{base_url}{settings.MEDIA_URL}{saved_path}" #local
                        #file_url = f"http:{settings.MEDIA_ROOT}/{saved_path}" #1.200
                    
                    outslip_image = OutslipImagesModel.objects.using(db_alias).create(
                        upload_files=file_url,
                        trip_ticket_id = trip_ticket_id,
                        trip_ticket_detail_id = trip_ticket_detail_id,
                        upload_remarks = remark,
                        upload_text = upload_txt,  
                        created_by=user_id,
                        created_date=timezone.now(),
                        updated_by=user_id,
                        updated_date=timezone.now(),
                        branch_id=branch_id
                    )
                    uploaded_files.append(OutslipImagesSerializer(outslip_image).data)
                    trip_details.is_posted = True
                    if db_alias == 'tsl_db':
                        logger.warning(f"dede {is_delivered}")
                        trip_details.is_delivered = is_delivered
                        if is_delivered == False:
                            trip_details.received_by = 'No Receiver/Cancelled'
                        else:
                            trip_details.received_by = received_by
                        trip_details.received_date = timezone.now()
                    trip_details.save() 
                except Exception as e:
                    errors.append({'upload_image': upload_image.name, 'error':str(e)})
            else:
                errors.append({'upload_image': upload_image.name, 'errors': serializer.errors})
        
        if uploaded_files:
            return Response({
                'message': 'Upload success',
                'uploaded_files': uploaded_files,
                'errors': errors if errors else None
            }, status=status.HTTP_201_CREATED)
        return Response({'error': 'All images failed to upload', 'details': errors}, status=status.HTTP_400_BAD_REQUEST)
def reverse_geocode(lat, lon):
        url = "https://us1.locationiq.com/v1/reverse"
        params = {
            'key' : 'pk.290fe86c4236d073d5c6996361d7d23d',
            'lat': lat,
            'lon': lon,
            'format': 'json'
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    


class CheckClockInView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.user_id
        db_alias = get_db_alias(request)
        current_date = timezone.now().date()
        trip_ticket_id = request.query_params.get('trip_ticket_id')
        branch_id = request.query_params.get('branch_id')
        print(f"Checking clock-in for: user={user_id}, trip={trip_ticket_id}, branch={branch_id}")
        exists = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by=user_id,
            trip_ticket_id=trip_ticket_id,
            branch_id=branch_id,
        ).exists()
        
        clockout_exists = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by=user_id,
            trip_ticket_id=trip_ticket_id,
            branch_id=branch_id,
            time_out__isnull=False
        ).exists()
        reclockin_exists = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by = user_id,
            trip_ticket_id= trip_ticket_id,
            branch_id = branch_id,
            time_in__date=current_date
        ).count()>1
        reclockout_exists = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by=user_id,
            trip_ticket_id=trip_ticket_id,
            branch_id=branch_id,
            time_in__date=current_date,
            time_out__isnull=False
        ).count()>1 
        return Response({'has_clocked_in': exists,
        'has_clocked_out':clockout_exists,
        'has_reclocked_in': reclockin_exists,
        'has_reclocked_out': reclockout_exists})

class TripTicketReceiveView(APIView):
    permission_classes = [IsAuthenticated]
    def post (self, request):
        try:
            db_alias = get_db_alias(request)
            
            receivingData = json.loads(request.data.get('receiving_data', '[]'))
            user_id = request.user.user_id
            trip_ticket_detail_id = receivingData[0]['trip_ticket_detail_id']
            #logger.warning("pjuke", trip_ticket_detail_id)
            has_upload = OutslipImagesModel.objects.using(db_alias).filter(
            trip_ticket_detail_id = trip_ticket_detail_id,
            created_by=user_id,
            ).first()
            
            created_ids = []
            
        
            if has_upload:
                return Response(
                    {f"You have already submitted, you can't submit anymore."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            for item in receivingData:
                new_record = TripTicketDetailReceivingModel.objects.using(db_alias).create(
                    server_id = 1,
                    trip_ticket_id=item['trip_ticket_id'],
                    trip_ticket_detail_id=item['trip_ticket_detail_id'],
                    ref_trans_id=item['ref_trans_id'],
                    ref_trans_no=item['ref_trans_no'],
                    trans_code_id=item['trans_code_id'],
                    item_id=item['item_id'],
                    item_qty=item['item_qty'],
                    doc_qty=float(item.get('doc_qty', item['item_qty'])), 
                    ref_trans_detail_id=item['ref_trans_detail_id'],
                    ref_trans_detail_pkg_id=item['ref_trans_detail_pkg_id'],
                    i_trans_no=item['i_trans_no'],
                    p_trans_no=item['p_trans_no'],
                    main_item=item['main_item'],
                    component_item=item['component_item'],
                    ser_bat_no=item['ser_bat_no'],
                    batch_no=item['batch_no'],
                    serbat_id=item['serbat_id'],
                    created_by = user_id,
                    created_date=timezone.now(),
                    updated_by = user_id,
                    updated_date=timezone.now(),
                )
                created_ids.append(new_record.receiving_id)
            return Response ({"message": "insucc"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ClockInAttendance(APIView):
    permission_classes = [IsAuthenticated]
    def post (self, request):
        data = request.data
        user_id = data['created_by']
        trip_ticket_id=data.get('trip_ticket_id')
        latitude = data.get('latitude_in')
        longitude = data.get('longitude_in')
        branch_id=data.get('branch_id')
        #current_date = datetime.now().date()
        if not latitude or not longitude:
            return Response({"error": "Latitude and longitude are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            db_alias = get_db_alias(request)
            
            if db_alias == 'default':
                has_posted = TripDetailsModel.objects.using(db_alias).filter(
                    trip_ticket_id = trip_ticket_id,
                    branch_id = branch_id,
                    is_posted = True
                ).exists()
            else:
                has_posted = TripDetailsModel.objects.using(db_alias).filter(
                    trip_ticket_id = trip_ticket_id,
                    entity_id = branch_id,
                    is_posted = True
                ).exists()
            no_clock_out = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by=user_id,
            time_out__isnull=True
            ).exclude(branch_id=branch_id).first()

            if no_clock_out:
                trip_ticket_no = TripTicketModel.objects.using(db_alias).filter(trip_ticket_id=no_clock_out.trip_ticket_id).values_list('trip_ticket_no', flat=True).first()
                return Response(
                    {"error": f"You haven't clocked out at Trip Ticket No:{trip_ticket_no} Branch ID:{no_clock_out.branch_id}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                has_clocked_in = TripTicketBranchLogsModel.objects.using(db_alias).filter(
                        created_by=user_id,
                       # created_date__date=current_date,
                        trip_ticket_id=trip_ticket_id,
                        branch_id= branch_id
                    ).exists()
                if has_clocked_in:
                    return Response(
                        {"error": f"You have already clocked in at {has_clocked_in.time_in}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            if has_posted:
                return Response (
                    {"error": f"Someone is already delivering in this branch "},
                    status=status.HTTP_400_BAD_REQUEST
                )
            geo_start = time.perf_counter()
            location_data = reverse_geocode(data['latitude_in'], data['longitude_in'])
            location_in = location_data.get('display_name')
            #logger.warning(f"🌍 Reverse geocode time: {(time.perf_counter() - geo_start) * 1000:.2f} ms")
            TripTicketBranchLogsModel.objects.using(db_alias).create(
                server_id=1,
                trip_ticket_id=data['trip_ticket_id'],
                branch_id=data['branch_id'],
                time_in=timezone.now(),
                created_by=data['created_by'],
                created_date=timezone.now(),
                updated_date=timezone.now(),
                updated_by=data['created_by'],
                location_in=location_in,
                ip_address_in='',
                latitude_in=data['latitude_in'],
                longitude_in=data['longitude_in'],
            )
            #logger.warning(f"✅ Total request time: {(time.perf_counter() - start_time) * 1000:.2f} ms")
            return Response ({"message": "insucc"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        
        
class UndoClockInAttendance(APIView):
    permission_classes = [IsAuthenticated]
    def post (self, request):
        data = request.data
        user_id = data['created_by']
        trip_ticket_id=data.get('trip_ticket_id')
        branch_id=data.get('branch_id')
        db_alias = get_db_alias(request)
        
        print(f"use2r", user_id)
        try:
            has_clocked_out = TripTicketBranchLogsModel.objects.using(db_alias).filter(
                created_by=user_id,
                trip_ticket_id=trip_ticket_id,
                branch_id= branch_id,
                time_out__isnull=False
            ).exists()
            has_clock_in = TripTicketBranchLogsModel.objects.using(db_alias).filter(
                created_by=user_id,
                trip_ticket_id=trip_ticket_id,
                branch_id= branch_id,
                time_in__isnull=False
            ).first()
           
            has_upload = OutslipImagesModel.objects.using(db_alias).filter(
                created_by=user_id,
                trip_ticket_id=trip_ticket_id,
                branch_id=branch_id,
            ).exists()
            
            if has_upload:
                return Response (
                    {"error": f"You have already uploaded here you can't remove your clock in"},
                    status=status.HTTP_400_BAD_REQUEST
                )            
            if has_clocked_out:
                return Response (
                    {"error": f"You have already clocked out you can't remove your clock in"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if has_clock_in:
                TripTicketBranchLogsSpoiledModel.objects.using(db_alias).create(
                    time_in = has_clock_in.time_in,
                    created_by = user_id,
                    created_date = timezone.now(),
                    updated_by = user_id,
                    updated_date = timezone.now(),
                    posted_by = has_clock_in.posted_by,
                    posted_date = has_clock_in.posted_date,
                    is_fap = has_clock_in.is_fap,
                    is_candis = has_clock_in.is_candis,
                    is_posted = has_clock_in.is_posted,
                    location_in = has_clock_in.location_in,
                    ip_address_in = has_clock_in.ip_address_in,
                    location_out = has_clock_in.location_out,
                    ip_address_out = has_clock_in.ip_address_out,
                    latitude_in = has_clock_in.latitude_in,
                    latitude_out = has_clock_in.latitude_out,
                    longitude_in = has_clock_in.longitude_in,
                    longitude_out = has_clock_in.longitude_out,
                    branch_id=branch_id,
                    trip_ticket_id = has_clock_in.trip_ticket_id,
                )
            TripTicketBranchLogsModel.objects.using(db_alias).filter(
                created_by=user_id,
                trip_ticket_id=trip_ticket_id,
                branch_id=branch_id,
                time_out__isnull=True,
            ).delete()
            return Response ({"message": "insucc"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
class ClockOutAttendance(APIView):
    permission_classes = [IsAuthenticated]
    def post (self, request):
        start_time = time.perf_counter()
        data = request.data
        user_id = request.user.user_id
        trip_ticket_id=data.get('trip_ticket_id')
        branch_id=data.get('branch_id')
        db_alias = get_db_alias(request)
        reason = data.get('reason')
        #current_date = datetime.now().date()
        
        try:
           
           
            has_clocked_in = TripTicketBranchLogsModel.objects.using(db_alias).filter(
                created_by=user_id,
                #created_date__date=current_date,
                trip_ticket_id=trip_ticket_id,
                branch_id=branch_id
            ).first()
            
            if not has_clocked_in:
                return Response (
                    {"error": "You must clock in before clocking out."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if has_clocked_in.time_out:
                return Response(
                    {"error": f"You have already clocked out at {has_clocked_in.time_out}."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if db_alias == 'tsl_db':
                trip_details = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id, entity_id=branch_id)
            else:
                trip_details = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id, branch_id=branch_id)
         
            if not reason:
                for detail in trip_details:
                    if not OutslipImagesModel.objects.using(db_alias).filter(
                    trip_ticket_id= trip_ticket_id,
                    trip_ticket_detail_id=detail.trip_ticket_detail_id,
                    branch_id=detail.branch_id if db_alias != 'tsl_db' else detail.entity_id,
                    ).first():
                        return Response(
                       {"error": f"Upload missing for outslip #{detail.ref_trans_no}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
               has_clocked_in.reason = reason
            
            latitude = data.get('latitude_out')
            longitude = data.get('longitude_out')
            location_data = reverse_geocode(data['latitude_out'], data['longitude_out'])
            location_out = location_data.get('display_name')
            #logger.warning(f"🌍 Reverse geocode time: {(time.perf_counter() - geo_start) * 1000:.2f} ms")
            has_clocked_in.time_out = timezone.now()
            has_clocked_in.updated_by = user_id
            has_clocked_in.updated_date = timezone.now()
            has_clocked_in.location_out = location_out
            has_clocked_in.ip_address_out = ''
            has_clocked_in.latitude_out = latitude
            has_clocked_in.longitude_out = longitude
            has_clocked_in.save()
            #logger.warning(f"✅ Total request time: {(time.perf_counter() - start_time) * 1000:.2f} ms")
            return Response ({"message": "insucc"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

class TripTicketReports(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        db_alias = get_db_alias(request)
        trip_ticket_no = request.query_params.get('trip_ticket_no')

        if not trip_ticket_no:
            return Response ({"error": "Trip Ticket No. is required."}, status=400)
        try:
            trip_ticket =TripTicketModel.objects.using(db_alias).filter(
                trip_ticket_no = trip_ticket_no).first()
            if not trip_ticket:
                    return Response({"Error": "Trip ticket not found."}, status= 404)                
            
            trip_ticket_id = trip_ticket.trip_ticket_id
            
            tripdetail_data = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id)
            if not tripdetail_data.exists():
                    return Response({"error": "No trip details found."}, status=404)
            driver_ids = set()
            if trip_ticket.entity_id:
                driver_ids.add(trip_ticket.entity_id)
            if trip_ticket.asst_entity_id:
                driver_ids.add(trip_ticket.asst_entity_id)
            if trip_ticket.dispatched_by:
                driver_ids.add(trip_ticket.dispatched_by)
            
            drivers = TripDriverModel.objects.using(db_alias).filter(
                entity_id__in=list(driver_ids)
            )
            driver_mapping = {driver.entity_id: driver.entity_name for driver in drivers}
            lastBranchRecord = TripTicketBranchLogsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id).order_by('-created_date').first()
            branch_name = None
            if lastBranchRecord:
                branch = TripBranchModel.objects.using(db_alias).filter(branch_id=lastBranchRecord.branch_id).first()
                branch_name = branch.branch_name if branch else None
                
            tripdetail_serializer = TripDetailsSerializer(tripdetail_data, many=True)
            tripData = []
            for detail in tripdetail_serializer.data:
                trip_detail = detail.copy()
                trip_detail.update({
                    'entity_name': driver_mapping.get(trip_ticket.entity_id, ''),
                    'asst_entity_name': driver_mapping.get(trip_ticket.asst_entity_id, ''),
                    'dispatcher': driver_mapping.get(trip_ticket.dispatched_by, ''),
                    'plate_no': trip_ticket.plate_no,
                    'last_branch': branch_name,
                    'last_branch_time' : lastBranchRecord.updated_date if lastBranchRecord else None,
                    'encoded_date': trip_ticket.updated_date,
                    'lat': lastBranchRecord.latitude_in,
                    'long': lastBranchRecord.longitude_in,

                })
                tripData.append(trip_detail)
            if not tripdetail_data.exists():
                return Response({"error": "Trip ticket not found."}, status=404)
        except ValueError:
            return Response({"error": "Invalid ID Format."}, status=400)
        
        return Response ({'tripdetails': tripData})
    

class BranchReportsView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        db_alias = get_db_alias(request)
        
        trip_ticket_no = request.query_params.get('trip_ticket_no')
        if not trip_ticket_no:  
            return Response({"error": "Trip Ticket No. is required."}, status=400)
        
        try:
           
            trip_ticket =TripTicketModel.objects.using(db_alias).filter(
            trip_ticket_no = trip_ticket_no).first()
            tripdetail_data = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket.trip_ticket_id)
            
            if not tripdetail_data.exists():
                return Response({"error": "Trip ticket not found."}, status=404)
        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)
        
        tripdetail_serializer = TripDetailsSerializer(tripdetail_data, many=True)
        tripdetails = tripdetail_serializer.data

        branch_ids = list(set([detail['branch_id'] for detail in tripdetails])) #convert to list and remove duplicates of branch id

        branch_data = TripBranchModel.objects.using(db_alias).order_by('branch_name').filter(branch_id__in=branch_ids) # match
        branch_serializer = TripBranchSerializer(branch_data, many=True)


        response_data = [ 
            { 
            'branch_id': branch['branch_id'], 
            'branch_name': branch['branch_name'] 
            } 
            for branch in branch_serializer.data 
        ]
        return Response(response_data)

class TripTicketDetailReports(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        db_alias = get_db_alias(request)
        
        trip_ticket_no = request.query_params.get('trip_ticket_no')
        branch_id = request.query_params.get('branch_id')
        
        if not trip_ticket_no:
            return Response({"error": "Trip Ticket No. is required."}, status=400)
        try:
            trip_ticket =TripTicketModel.objects.using(db_alias).filter(
            trip_ticket_no = trip_ticket_no).first()
            tripdetail_data = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket.trip_ticket_id, branch_id=branch_id)
            
            if not tripdetail_data.exists():
                return Response({"error": "Trip ticket not found."}, status=404)
        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)
        
        tripdetail_serializer = TripDetailsSerializer(tripdetail_data, many=True)
        tripdetails = tripdetail_serializer.data

        return Response(tripdetails)

class AttendanceReports(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        db_alias = get_db_alias(request)
              
        trip_ticket_id = request.query_params.get('trip_ticket_id')
        branch_id = request.query_params.get('branch_id')
        try:

            user_logs = TripTicketBranchLogsModel.objects.using(db_alias).order_by('-log_id').filter(trip_ticket_id=trip_ticket_id, branch_id = branch_id)
        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)
        userlogs_serializer = BranchLogsSerializer(user_logs, many=True)

        return Response(userlogs_serializer.data)
    
class InitialReports(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        db_alias = get_db_alias(request)

        try: 
            latest_log = TripTicketBranchLogsModel.objects.using(db_alias).order_by('-created_date').first()

            initial_trip = TripTicketModel.objects.using(db_alias).filter(trip_ticket_id=latest_log.trip_ticket_id).order_by('-updated_date').first()
            driver_ids = set()
            if initial_trip.entity_id:
                driver_ids.add(initial_trip.entity_id)
            if initial_trip.asst_entity_id:
                driver_ids.add(initial_trip.asst_entity_id)
            if initial_trip.dispatched_by:
                driver_ids.add(initial_trip.dispatched_by)
            
            drivers = TripDriverModel.objects.using(db_alias).filter(
                entity_id__in=list(driver_ids)
            )
            driver_mapping = {driver.entity_id: driver.entity_name for driver in drivers}
            
            branch_name = None
            if latest_log:
                branch = TripBranchModel.objects.using(db_alias).filter(branch_id=latest_log.branch_id).first()
                branch_name = branch.branch_name if branch else None 
            logger.warning(f"trip{initial_trip} branch{latest_log}")
            trip_serializer = TripTicketSerializer(initial_trip)
            tripData = []
            if isinstance(trip_serializer.data, dict):
                trip_ticket = trip_serializer.data.copy() 
                trip_ticket.update({
                    'entity_name': driver_mapping.get(initial_trip.entity_id, ''),
                    'asst_entity_name': driver_mapping.get(initial_trip.asst_entity_id, ''),
                    'dispatcher': driver_mapping.get(initial_trip.dispatched_by, ''),
                    'plate_no': initial_trip.plate_no,
                    'last_branch': branch_name,
                    'last_branch_time': latest_log.updated_date if latest_log else None,
                    'encoded_date': initial_trip.updated_date,
                    'lat': latest_log.latitude_in,
                    'long': latest_log.longitude_in
                })
                tripData.append(trip_ticket)
        except ValueError:
            return Response({'error': 'Invalid.'}, status=400)
        return Response ({'latestLog': tripData})
#####################TSL DMS############################

class TripCustomerView(APIView): #TSL ONLY
    permission_classes = [AllowAny]
   
    def get(self, request):
        db_alias = get_db_alias(request)
        trip_ticket_id = request.query_params.get('id')
        trip_ticket_no = request.query_params.get('trip_ticket_no')
        if not trip_ticket_id and not trip_ticket_no:  
            return Response({"error": "ID and No. is required."}, status=400)
        
        try:
            if trip_ticket_no and not trip_ticket_id:
                trip_ticket = TripTicketModel.objects.using(db_alias).filter(
                    trip_ticket_no = trip_ticket_no
                ).first()
                
                if not trip_ticket:
                    return Response({"error": "Trip ticket not found."}, status=404)
                
                trip_ticket_id = trip_ticket.trip_ticket_id
                
            tripdetail_data = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id)
            if not tripdetail_data.exists():
                return Response({"error": "Trip ticket not found."}, status=404)
        except ValueError:
            return Response({"error": "Invalid ID Format."}, status=400)

        tripdetail_serializer = TripDetailsSerializer(tripdetail_data, many=True)
        tripdetails = tripdetail_serializer.data
        address_mapping = {
            detail['entity_id']: detail['full_address']
            for detail in tripdetail_serializer.data
            if detail.get('entity_id') and detail.get('full_address')
        }
        
        customer_ids = list(set([detail['entity_id'] for detail in tripdetails]))
        
        customer_data = TripCustomerModel.objects.using(db_alias).order_by('entity_name').filter(entity_id__in=customer_ids)
        customer_serializer = CustomerMFSerializer(customer_data, many=True)

        response_data = [
            {
                'entity_id': customer['entity_id'],
                'entity_name': customer['entity_name'],
                'full_address': address_mapping.get(customer['entity_id'])
            }
            for customer in customer_serializer.data
        ]
        return Response(response_data)

class CustomerDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        db_alias = get_db_alias(request)

        trip_ticket_id = request.query_params.get('trip_ticket_id')
        customer_id = request.query_params.get('entity_id')

        if not trip_ticket_id and not customer_id:
            return Response ({"error": "trip ticket id is required"})

        try: 
            customer_details = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id,
            entity_id=customer_id)
            customer_serializer = TripDetailsSerializer(customer_details, many=True)
  
            logger.warning(customer_serializer.data)
            return Response(customer_serializer.data)
        except ValueError:
            return Response({"error": "Invalid ID format."}, status=400)
class ManageAttendanceTSL(APIView):
    permission_classes = [IsAuthenticated]
    def get (self, request):
        user = request.user
        db_alias = get_db_alias(request)

        user_logs = TripTicketBranchLogsModel.objects.using(db_alias).order_by('-log_id').filter(created_by = user.user_id)
        trip_ticket_ids = user_logs.values_list('trip_ticket_id', flat=True).distinct()
        branch_ids = user_logs.values_list('branch_id', flat=True).distinct()       
        trip_tickets = TripTicketModel.objects.using(db_alias).filter(trip_ticket_id__in = trip_ticket_ids)
        trip_details = TripDetailsModel.objects.using(db_alias).filter(entity_id__in= branch_ids)
        ticket_number_map = {
            ticket.trip_ticket_id:ticket.trip_ticket_no
            for ticket in trip_tickets
        }
        trip_detail_map = {
            detail.entity_id:detail.entity_name
            for detail in trip_details
        }
        userlogs_serializer = BranchLogsSerializer(user_logs, many=True)

        response_data = []
        for log_data in userlogs_serializer.data:
            log_data['trip_ticket_no'] = ticket_number_map.get(log_data['trip_ticket_id'], '')
            log_data['entity_name'] = trip_detail_map.get(log_data['branch_id'], '')
            response_data.append(log_data)
        return Response({'userlogs': response_data})
    
        
class ReclockInAttendance(APIView):
    permission_classes = [IsAuthenticated]
    def post (self, request):
        data = request.data
        user_id = data['created_by']
        trip_ticket_id=data.get('trip_ticket_id')
        latitude = data.get('latitude_in')
        longitude = data.get('longitude_in')
        branch_id=data.get('branch_id')
        #current_date = datetime.now().date()
        if not latitude or not longitude:
            return Response({"error": "Latitude and longitude are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            db_alias = get_db_alias(request)
            no_clock_out = TripTicketBranchLogsModel.objects.using(db_alias).filter(
            created_by=user_id,
            time_out__isnull=True
            ).exclude(branch_id=branch_id).first()

            if no_clock_out:
                trip_ticket_no = TripTicketModel.objects.using(db_alias).filter(trip_ticket_id=no_clock_out.trip_ticket_id).values_list('trip_ticket_no', flat=True).first()
                return Response(
                    {"error": f"You haven't clocked out at Trip Ticket No:{trip_ticket_no} Branch ID:{no_clock_out.branch_id}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
           
           
            location_data = reverse_geocode(data['latitude_in'], data['longitude_in'])
            location_in = location_data.get('display_name')
            #logger.warning(f"🌍 Reverse geocode time: {(time.perf_counter() - geo_start) * 1000:.2f} ms")
            TripTicketBranchLogsModel.objects.using(db_alias).create(
                server_id=1,
                trip_ticket_id=data['trip_ticket_id'],
                branch_id=data['branch_id'],
                time_in=timezone.now(),
                created_by=data['created_by'],
                created_date=timezone.now(),
                updated_date=timezone.now(),
                updated_by=data['created_by'],
                location_in=location_in,
                ip_address_in='RETIME IN',
                latitude_in=data['latitude_in'],
                longitude_in=data['longitude_in'],
            )
            #logger.warning(f"✅ Total request time: {(time.perf_counter() - start_time) * 1000:.2f} ms")
            return Response ({"message": "insucc"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

 
class ReclockOutAttendance(APIView):
    permission_classes = [IsAuthenticated]
    def post (self, request):
        data = request.data
        user_id = request.user.user_id
        trip_ticket_id=data.get('trip_ticket_id')
        branch_id=data.get('branch_id')
        db_alias = get_db_alias(request)
        
        try:
            has_clocked_in = TripTicketBranchLogsModel.objects.using(db_alias).filter(
                created_by=user_id,
                #created_date__date=current_date,
                trip_ticket_id=trip_ticket_id,
                branch_id=branch_id,
                time_in__isnull=False,
                time_out__isnull=True,
            ).first()
            if db_alias == 'tsl_db':
                trip_details = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id, entity_id=branch_id)
            else:
                trip_details = TripDetailsModel.objects.using(db_alias).filter(trip_ticket_id=trip_ticket_id, branch_id=branch_id)
         
            for detail in trip_details:
                if not OutslipImagesModel.objects.using(db_alias).filter(
                trip_ticket_id= trip_ticket_id,
                trip_ticket_detail_id=detail.trip_ticket_detail_id,
                branch_id=branch_id,
                ).first():
                    return Response(
                    {"error": f"Upload missing for outslip #{detail.ref_trans_no}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
     
            
            latitude = data.get('latitude_out')
            longitude = data.get('longitude_out')
            location_data = reverse_geocode(data['latitude_out'], data['longitude_out'])
            location_out = location_data.get('display_name')
            #logger.warning(f"🌍 Reverse geocode time: {(time.perf_counter() - geo_start) * 1000:.2f} ms")
            has_clocked_in.time_out = timezone.now()
            has_clocked_in.updated_by = user_id
            has_clocked_in.updated_date = timezone.now()
            has_clocked_in.location_out = location_out
            has_clocked_in.ip_address_out = ''
            has_clocked_in.latitude_out = latitude
            has_clocked_in.longitude_out = longitude
            has_clocked_in.save()
            #logger.warning(f"✅ Total request time: {(time.perf_counter() - start_time) * 1000:.2f} ms")
            return Response ({"message": "insucc"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        


class CancelOutslipView(APIView):
    permission_classes = [IsAuthenticated]
    def post (self, request):
        try:
            db_alias = get_db_alias(request)
            
            receivingData = json.loads(request.data.get('receiving_data', '[]'))
            user_id = request.user.user_id
            trip_ticket_detail_id = receivingData[0]['trip_ticket_detail_id']
            #logger.warning("pjuke", trip_ticket_detail_id)
            has_upload = OutslipImagesModel.objects.using(db_alias).filter(
            trip_ticket_detail_id = trip_ticket_detail_id,
            created_by=user_id,
            ).first()
            
            created_ids = []
            
        
            if has_upload:
                return Response(
                    {f"You have already submitted, you can't submit anymore."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            for item in receivingData:
                new_record = TripTicketDetailReceivingModel.objects.using(db_alias).create(
                    server_id = 1,
                    trip_ticket_id=item['trip_ticket_id'],
                    trip_ticket_detail_id=item['trip_ticket_detail_id'],
                    ref_trans_id=item['ref_trans_id'],
                    ref_trans_no=item['ref_trans_no'],
                    trans_code_id=item['trans_code_id'],
                    item_id=item['item_id'],
                    item_qty=0,
                    doc_qty=float(item.get('doc_qty', item['item_qty'])), 
                    ref_trans_detail_id=item['ref_trans_detail_id'],
                    ref_trans_detail_pkg_id=item['ref_trans_detail_pkg_id'],
                    i_trans_no=item['i_trans_no'],
                    p_trans_no=item['p_trans_no'],
                    main_item=item['main_item'],
                    component_item=item['component_item'],
                    ser_bat_no=item['ser_bat_no'],
                    batch_no=item['batch_no'],
                    serbat_id=item['serbat_id'],
                    created_by = user_id,
                    created_date=timezone.now(),
                    updated_by = user_id,
                    updated_date=timezone.now(),
                )
                created_ids.append(new_record.receiving_id)
            return Response ({"message": "insucc"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



###WTPIRIS###
class LayerCursorPagination(CursorPagination):
    page_size = 25
    ordering = 'full_code'

class LayerMFView (APIView):
    permission_classes = [AllowAny]
    pagination_class = LayerCursorPagination

    def get(self, request):
        db_alias = get_db_alias(request)

        layers = LayerMFModel.objects.using(db_alias).all()
        search_query = request.query_params.get('search', None)
        if search_query:
            layers = layers.filter(Q(full_code__icontains=search_query))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(layers,request)

        layers_serializer = LayerMFSerializer(page, many=True)
        
        return paginator.get_paginated_response(layers_serializer.data)
    
class SaveBarcode(APIView):
    permission_classes = [AllowAny]

    def post (self, request):
        db_alias = get_db_alias(request)
        layer_id = request.data.get('layer_id')
        barcode = request.data.get('barcode')
        user_id = request.data.get('created_by')
        header_id = request.query_params.get('id')

        itemMF = ItemMFModel.objects.using(db_alias).all().filter(barcode=barcode).first()
        if not itemMF:
            return Response({'error': 'Item does not exist'}, status=  400)
        try:
            if not header_id:
                max_header = InventoryCountRowManagerModel.objects.using(db_alias).aggregate(Max('header_no'))['header_no__max'] or 0
                new_header = InventoryCountRowManagerModel.objects.using(db_alias).create(
                    server_id=1,
                    header_no = max_header + 1,
                    company_id = 3,
                    mf_status_id=4,
                    created_by=user_id,
                    created_date=timezone.now(),
                    updated_by=user_id,
                    updated_date=timezone.now()
                )
                header_id = new_header.header_id
            ItemFullCountScanModel.objects.using(db_alias).create(
                server_id=1,
                layer_id=layer_id,
                item_id = itemMF.item_id,
                header_id = header_id,
                barcode = barcode,
                item_qty= 1,
                created_by = user_id,
                created_date = timezone.now(),
                updated_by = user_id,
                updated_date = timezone.now()
            )
            return Response({"message":"barbar"}, status=status.HTTP_201_CREATED)
        except Exception as e:
                return Response(
                    logger.error(f"Failed to save barcode: {str(e)}"),
                    {'error': f'Failed to save barcode: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
class DeleteBarcode(APIView):
    permission_classes = [AllowAny]

    def post(self,request):
        db_alias = get_db_alias(request)
        tmp_fullcount_id = request.data.get('tmp_fullcount_id')
        try:
            item_fullcount = ItemFullCountScanModel.objects.using(db_alias).filter(tmp_fullcount_id = tmp_fullcount_id).first()
            serial_fullcount = SerialFullCountScanModel.objects.using(db_alias).all().filter(tmp_fullcount_id = tmp_fullcount_id)
            if not item_fullcount:
                return Response({'error': 'Item does not exist'}, status=  400)
          
            item_fullcount.delete()
            serial_fullcount.delete()
            return Response ({"message": "dede"}, status = status.HTTP_200_OK)
        except Exception as e:
            return Response(
                logger.error(f"Failed to delete: {str(e)}"),
                {'error': f'Failed to delete barcode: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

class DeleteSerbat(APIView):
    permission_classes = [AllowAny]

    def post(self,request):
        db_alias = get_db_alias(request)
        serial_fullcount_id = request.data.get('serial_fullcount_id')
        user_id = request.data.get('created_by')
        try:
            item_code = SerialFullCountScanModel.objects.using(db_alias).filter(serial_fullcount_id=serial_fullcount_id).first()
            barcode = ItemFullCountScanModel.objects.using(db_alias).filter(tmp_fullcount_id = item_code.tmp_fullcount_id).first()

            if not item_code:
                return Response({'error': 'Serial does not exist'}, status=  400)
           
            item_code.delete()
            total_quantity = SerialFullCountScanModel.objects.using(db_alias).filter(
                tmp_fullcount_id=item_code.tmp_fullcount_id
            ).aggregate(
                total_quantity=Sum('quantity')
            )['total_quantity'] or 0

            barcode.item_qty = total_quantity
            barcode.updated_by = user_id
            barcode.updated_date = timezone.now()
            barcode.save(using=db_alias)
            return Response ({"message": "dede"}, status = status.HTTP_200_OK)
        except Exception as e:
            return Response(
                logger.error(f"Failed to delete: {str(e)}"),
                {'error': f'Failed to delete barcode: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        
class FullCountBarcodeView(APIView):
    permission_classes = [AllowAny]

    def get (self,request):
        db_alias = get_db_alias(request)
        header_id = request.query_params.get('id')
        barcode = ItemFullCountScanModel.objects.using(db_alias).all().order_by('-tmp_fullcount_id').filter(header_id=header_id)
        items = ItemMFModel.objects.using(db_alias).all()
        layers = LayerMFModel.objects.using(db_alias).all()
        layer_mapping = {layer.layer_id: layer.full_code for layer in layers}
        item_mapping = {item.item_id: item.item_description for item in items}
        barcode_serializer = ItemFullCountScanSerializer(barcode, many=True)
        for fc in barcode_serializer.data:
            fc['item_description'] = item_mapping.get(fc['item_id'], '')
            fc['full_code'] = layer_mapping.get(fc['layer_id'], '')

        return Response({'barcodeItem': barcode_serializer.data})
    
class InventoryCountListView(APIView):
    permission_classes = [AllowAny]

    def get (self,request):
        db_alias = get_db_alias(request)
        header = InventoryCountRowManagerModel.objects.using(db_alias).all().order_by('-created_date')
        users = User.objects.using(db_alias).all()

        user_mapping = {user.user_id: user.user_name for user in users}
        header_serializer = InventoryCountRowManagerSerializer(header, many=True)

        for user in header_serializer.data:
            user['user_name'] = user_mapping.get(user['created_by'], '')
        return Response(header_serializer.data)

class FullCountSerialView(APIView):
    permission_classes = [AllowAny]

    def get (self,request):
        db_alias = get_db_alias(request)
        tmp_fullcount_id = request.query_params.get('id')
        serbat = SerialFullCountScanModel.objects.using(db_alias).all().order_by('-created_date').filter(tmp_fullcount_id=tmp_fullcount_id)
        serbat_serializer = SerialFullCountScanSerializer(serbat, many=True)
        return Response({'serbatItem': serbat_serializer.data})

class SelectedItemCodeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        db_alias = get_db_alias(request)
        tmpID = request.query_params.get('id')
        selectedTmpID = ItemFullCountScanModel.objects.using(db_alias).filter(tmp_fullcount_id=tmpID).first()
        items = ItemMFModel.objects.using(db_alias).all()
        layers = LayerMFModel.objects.using(db_alias).all()
        layer_mapping = {layer.layer_id: layer.full_code for layer in layers}
        item_mapping = {item.item_id: item.item_description for item in items}
        tmpID_serializer = ItemFullCountScanSerializer(selectedTmpID)
        response_data = tmpID_serializer.data

        response_data['item_description'] = item_mapping.get(response_data['item_id'], '')
        response_data['full_code'] = layer_mapping.get(response_data['layer_id'], '')


        return Response({'selectedItemCode': [response_data]})

class SaveSerbat(APIView):
    permission_classes = [AllowAny]

    def post (self, request):
        db_alias = get_db_alias(request)
        serial = request.data.get('serial')
        batch = request.data.get('batch')
        user_id = request.data.get('created_by')
        quantity = request.data.get('quantity', 1)
        tmp_fullcount_id = request.query_params.get('id')

        try:
            if tmp_fullcount_id:
                item_code = ItemFullCountScanModel.objects.using(db_alias).filter(tmp_fullcount_id=tmp_fullcount_id).first()
            if not item_code:
                return Response({'error': 'Item not found'}, status=  400)

            SerialFullCountScanModel.objects.using(db_alias).create(
                server_id=1,
                tmp_fullcount_id=tmp_fullcount_id,
                item_id = item_code.item_id,
                header_id = item_code.header_id,
                layer_id = item_code.layer_id,
                item_code = item_code.barcode,
                serial_code = serial,
                batch_no = batch,
                quantity = quantity,
                created_by = user_id,
                created_date = timezone.now(),
                updated_by = user_id,
                updated_date = timezone.now()
            )
            total_quantity = SerialFullCountScanModel.objects.using(db_alias).filter(
                tmp_fullcount_id=tmp_fullcount_id
            ).aggregate(
                total_quantity=Sum('quantity')
            )['total_quantity'] or 0

            # Update the item quantity
            item_code.item_qty = total_quantity
            item_code.updated_by = user_id
            item_code.updated_date = timezone.now()
            item_code.save(using=db_alias)
            return Response({"message":"serbatbat"}, status=status.HTTP_201_CREATED)
        except Exception as e:
                return Response(
                    logger.error(f"Fail4ed to save serbat: {str(e)}"),
                    {'error': f'Failed to save serbat: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
class EditBarcodeQty(APIView):
    permission_classes = [AllowAny]

    def post (self, request):
        db_alias = get_db_alias(request)
        quantity = request.data.get('quantity')
        serial_fullcount_id = request.data.get('serial_fullcount_id')
        user_id = request.data.get('created_by')

        try:
            if serial_fullcount_id:
                item_code = SerialFullCountScanModel.objects.using(db_alias).filter(serial_fullcount_id=serial_fullcount_id).first()
                barcode = ItemFullCountScanModel.objects.using(db_alias).filter(tmp_fullcount_id=item_code.tmp_fullcount_id).first()

            # Update the item quantity
            item_code.quantity = quantity
            item_code.updated_by = user_id
            item_code.updated_date = timezone.now()
            item_code.save(using=db_alias)
            total_quantity = SerialFullCountScanModel.objects.using(db_alias).filter(
                tmp_fullcount_id=item_code.tmp_fullcount_id
            ).aggregate(
                total_quantity=Sum('quantity')
            )['total_quantity'] or 0
            barcode.item_qty = total_quantity
            barcode.updated_by = user_id
            barcode.updated_date = timezone.now()
            barcode.save(using=db_alias)
            return Response({"message":"eded"}, status=status.HTTP_201_CREATED)
        except Exception as e:
                return Response(
                    logger.error(f"Fail4ed to save serbat: {str(e)}"),
                    {'error': f'Failed to save serbat: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
