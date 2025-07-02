from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Max
from django.contrib.auth.hashers import make_password, check_password


class User(AbstractBaseUser):
    user_id = models.BigIntegerField(primary_key=True)
    user_code = models.CharField(max_length=30, unique=True)
    password = models.CharField(max_length=255)
    first_name = models.CharField(max_length=100) 
    middle_name = models.CharField(max_length=100) 
    last_name = models.CharField(max_length=100) 
    user_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_super = models.BooleanField(default=True)
    USERNAME_FIELD = 'user_code'
    last_login = None  
    def get_username(self):  
        return self.user_code

    class Meta:
        managed = False
        db_table = 'sys_user'
    

 

class TripTicketModel(models.Model):
    trip_ticket_id = models.BigIntegerField(primary_key=True)
    trip_ticket_no = models.BigIntegerField()
    vehicle_id =models.BigIntegerField()
    plate_no = models.CharField(max_length=20)
    entity_id = models.BigIntegerField()
    asst_entity_id = models.BigIntegerField()
    trip_ticket_date = models.DateTimeField()
    trip_ticket_delivery_type_id = models.BigIntegerField()
    dispatched_by = models.BigIntegerField()
    remarks = models.TextField()
    is_posted = models.BooleanField()
    is_final_trip = models.BooleanField()
    updated_date = models.DateTimeField()
    class Meta:
        db_table = 'scm_tr_trip_ticket'
        managed = False

class TripDriverModel(models.Model):
    entity_id = models.BigIntegerField(primary_key=True)
    entity_name = models.CharField(max_length=255)
    
    
    class Meta:
        db_table = 'fin_mf_entity'
        managed = False

    
class TripDetailsModel(models.Model):
    trip_ticket_id = models.BigIntegerField()
    branch_id = models.BigIntegerField()
    branch_name = models.CharField(max_length=255)
    entity_id = models.BigIntegerField()
    entity_name = models.CharField(max_length=255)
    trip_ticket_detail_id = models.BigAutoField(primary_key=True)
    ref_trans_date = models.DateTimeField()
    ref_trans_id = models.BigIntegerField()
    ref_trans_no = models.CharField(max_length=255)
    full_address = models.TextField()
    trans_name = models.CharField(max_length=255)
    received_by = models.CharField(max_length=255)
    received_date = models.DateTimeField()
    remarks = models.TextField()
    branch_charges = models.DecimalField(max_digits=18, decimal_places=2)
    document_amount = models.DecimalField(max_digits=18, decimal_places=2)
    detail_volume = models.DecimalField(max_digits=18, decimal_places=6)
    is_posted = models.BooleanField()
    is_delivered = models.BooleanField()
    updated_date = models.DateTimeField()
    created_date = models.DateTimeField()
    
    class Meta:
        db_table = 'scm_tr_trip_ticket_detail'
        managed = False

class TripBranchModel(models.Model):
    branch_id = models.BigIntegerField(primary_key=True)
    branch_name = models.CharField(max_length=255)
    
    class Meta:
        db_table = 'fin_mf_branch'
        managed = False

class TripCustomerModel(models.Model):
    entity_id = models.BigIntegerField(primary_key = True)
    entity_name = models.CharField(max_length=255)

    class Meta:
        db_table = 'fin_mf_entity'
        managed = False

class OutslipItemQtyModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    outslip_to_id = models.BigIntegerField() # ref_trans_id in scm_tr_trip_ticket_detail
    outslip_to_item_id = models.BigIntegerField(primary_key=True) #outslip ID = scm_Tr_to
    item_id = models.BigIntegerField(null=True, blank=True)
    item_qty = models.DecimalField(max_digits=12 ,decimal_places=4) 
    remarks = models.TextField(null=True, blank=True)
    class Meta:
        db_table ='scm_tr_outslip_to_item' 
        managed = False
        
class ItemMFModel(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    barcode = models.CharField(max_length=255, null=True, blank=True)
    item_description = models.CharField(max_length=450, null=True, blank=True)
    uom_id = models.BigIntegerField()
    
    class Meta:
        db_table = 'scm_mf_item'
        managed = False


class UOMMFModel(models.Model):
    uom_id = models.BigIntegerField(primary_key=True)
    uom_code = models.CharField(max_length=30)
    
    class Meta:
        db_table = 'scm_mf_uom'
        managed = False

class OutslipImagesModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    trip_ticket_id = models.BigIntegerField() #scm_tr_trip_ticket PK
    upload_id = models.BigAutoField(primary_key=True) #identity
    trip_ticket_detail_id = models.BigIntegerField()
    branch_id = models.BigIntegerField()
    upload_text = models.CharField(max_length=4000, null=True, blank=True)
    upload_remarks = models.CharField(max_length=4000, null=True, blank=True)
    upload_files = models.CharField(max_length=4000, null=True, blank=True)
    created_by = models.BigIntegerField() #sys_user
    created_date = models.DateTimeField()
    updated_by = models.BigIntegerField(null=True, blank=True) #sys_user
    updated_date = models.DateTimeField(null=True, blank=True)
    posted_by = models.BigIntegerField(null=True, blank=True) #sys_user
    posted_date = models.DateTimeField(null=True, blank=True)
    is_fap = models.BooleanField(default=False)
    is_candis = models.BooleanField(default=False)
    is_posted = models.BooleanField(default=False)
    class Meta:
        #db_table = 'scm_tr_outslip_to_images'
        db_table = 'scm_tr_trip_ticket_detail_images'
        managed = True
    """     constraints = [
                models.UniqueConstraint(fields=['server_id', 'trip_ticket_id'], name='outslip_images_composite_pk') #not working so manual it sa mssql
            ] """
    

class TripTicketBranchLogsModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    trip_ticket_id = models.BigIntegerField() #scm_tr_trip_ticket PK
    log_id = models.BigAutoField(primary_key=True) #identity
    time_in = models.DateTimeField()
    time_out = models.DateTimeField(null=True, blank=True)
    created_by = models.BigIntegerField() #sys_user
    created_date = models.DateTimeField()
    updated_by = models.BigIntegerField(null=True, blank=True) #sys_user
    updated_date = models.DateTimeField(null=True, blank=True)
    posted_by = models.BigIntegerField(null=True, blank=True) #sys_user
    posted_date = models.DateTimeField(null=True, blank=True)
    is_fap = models.BooleanField(default=False)
    is_candis = models.BooleanField(default=False)
    is_posted = models.BooleanField(default=False)
    location_in = models.CharField(max_length=255, null=True)
    ip_address_in = models.CharField(max_length=255,null=True)
    location_out = models.CharField(max_length=255, null=True)
    ip_address_out = models.CharField(max_length=255,null=True)
    latitude_in = models.FloatField(null=True, blank=True)
    latitude_out = models.FloatField(null=True, blank=True)  
    longitude_in = models.FloatField(null=True, blank=True)
    longitude_out = models.FloatField(null=True, blank=True)  
    branch_id = models.BigIntegerField() 
    reason = models.CharField(max_length=255,null=True)

    class Meta:
        db_table = 'scm_tr_trip_ticket_branch_logs'
        managed = True
    """     constraints = [
            models.UniqueConstraint(fields=['server_id', 'trip_ticket_id'], name='branch_logs_composite_pk') #not working so manual it sa mssql
        ]
"""

class TripTicketBranchLogsSpoiledModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    trip_ticket_id = models.BigIntegerField() #scm_tr_trip_ticket PK
    log_id = models.BigAutoField(primary_key=True) #identity
    time_in = models.DateTimeField()
    time_out = models.DateTimeField(null=True, blank=True)
    created_by = models.BigIntegerField() #sys_user
    created_date = models.DateTimeField()
    updated_by = models.BigIntegerField(null=True, blank=True) #sys_user
    updated_date = models.DateTimeField(null=True, blank=True)
    posted_by = models.BigIntegerField(null=True, blank=True) #sys_user
    posted_date = models.DateTimeField(null=True, blank=True)
    is_fap = models.BooleanField(default=False)
    is_candis = models.BooleanField(default=False)
    is_posted = models.BooleanField(default=False)
    location_in = models.CharField(max_length=255, null=True)
    ip_address_in = models.CharField(max_length=255,null=True)
    location_out = models.CharField(max_length=255, null=True)
    ip_address_out = models.CharField(max_length=255,null=True)
    latitude_in = models.FloatField(null=True, blank=True)
    latitude_out = models.FloatField(null=True, blank=True)  
    longitude_in = models.FloatField(null=True, blank=True)
    longitude_out = models.FloatField(null=True, blank=True)  
    branch_id = models.BigIntegerField()

    class Meta:
        db_table = 'scm_tr_trip_ticket_branch_logs_spoiled'
        managed = True
    """     constraints = [
            models.UniqueConstraint(fields=['server_id', 'trip_ticket_id'], name='branch_logs_composite_pk') #not working so manual it sa mssql
        ]
"""

class TripTicketDetailReceivingModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    receiving_id = models.BigAutoField(primary_key=True) #identity
    trip_ticket_id = models.BigIntegerField() 
    trip_ticket_detail_id = models.BigIntegerField()
    ref_trans_id = models.BigIntegerField()
    ref_trans_no = models.CharField(max_length=255, null=True)
    trans_code_id = models.BigIntegerField(null=True)
    item_id = models.BigIntegerField()
    item_qty = models.BigIntegerField()
    doc_qty = models.BigIntegerField()
    ref_trans_detail_id = models.BigIntegerField()
    ref_trans_detail_pkg_id = models.BigIntegerField(default=0)
    i_trans_no = models.BigIntegerField()
    p_trans_no = models.BigIntegerField()
    main_item = models.SmallIntegerField()
    component_item = models.SmallIntegerField()
    ser_bat_no = models.CharField(max_length=255, null=True)
    batch_no = models.CharField(max_length=255, null=True)
    serbat_id = models.BigIntegerField()
    created_by = models.BigIntegerField()
    created_date = models.DateTimeField()
    updated_by = models.BigIntegerField(null=True)
    updated_date = models.DateTimeField(null=True)
    posted_by = models.BigIntegerField(null=True)
    posted_date = models.DateTimeField(null=True)
    is_fap = models.BooleanField(default=False)
    is_candis = models.BooleanField(default=False)
    is_posted = models.BooleanField(default=False)

    class Meta:
        db_table = 'scm_tr_trip_ticket_detail_receiving'
        managed = False



###########SCANNER
class InventoryCountRowManagerModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    header_id = models.AutoField(primary_key=True)
    company_id = models.BigIntegerField(default=3)
    header_no = models.BigIntegerField()
    mf_status_id = models.SmallIntegerField()
    created_by = models.BigIntegerField()
    created_date = models.DateTimeField()
    updated_by = models.BigIntegerField()
    updated_date = models.DateTimeField()

    class Meta:
        db_table = 'scm_ir_inventory_count_rm'
        managed = False

class ItemFullCountScanModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    tmp_fullcount_id = models.AutoField(primary_key=True)
    header_id = models.BigIntegerField()
    layer_id = models.BigIntegerField()
    item_id = models.BigIntegerField()
    barcode = models.CharField(max_length=255, null=True)
    item_qty = models.DecimalField(max_digits=12 ,decimal_places=4) 
    created_by = models.BigIntegerField()
    created_date = models.DateTimeField()
    updated_by = models.BigIntegerField()
    updated_date = models.DateTimeField()
    
    
    class Meta:
        db_table = 'scm_ir_item_fullcount_scan'
        managed = False
    
class LayerMFModel(models.Model):
    mf_status_id = models.SmallIntegerField()
    layer_id = models.AutoField(primary_key=True)
    full_code = models.CharField(max_length=255, null=True)
    
    class Meta:
        db_table = 'scm_mf_layer'
        managed = False

class SerialFullCountScanModel(models.Model):
    server_id = models.BigIntegerField(default=1)
    serial_fullcount_id = models.AutoField(primary_key=True)
    tmp_fullcount_id = models.BigIntegerField()
    header_id = models.BigIntegerField()
    layer_id = models.BigIntegerField()
    item_id = models.BigIntegerField()
    quantity = models.BigIntegerField()
    item_code = models.CharField(max_length=255, null=True)
    serial_code = models.CharField(max_length=255, null=True)
    batch_no = models.CharField(max_length=255, null=True)
    serbat_id = models.BigIntegerField(null=True)
    created_by = models.BigIntegerField()
    created_date = models.DateTimeField()
    updated_by = models.BigIntegerField()
    updated_date = models.DateTimeField()
    
    class Meta:
        db_table = 'scm_ir_serial_fullcount_scan'
        managed = False