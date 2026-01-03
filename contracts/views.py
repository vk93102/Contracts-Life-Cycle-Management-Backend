"""
Contract API Views - Week 1 & Week 2 Endpoints
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import Contract, WorkflowLog
from .serializers import (
    ContractSerializer,
    ContractDetailSerializer,
    ContractDecisionSerializer,
    WorkflowLogSerializer
)
from authentication.r2_service import R2StorageService


class ContractListCreateView(APIView):
    """
    POST /api/v1/contracts/ - Create a new contract with file upload
    GET /api/v1/contracts/ - List all contracts for the tenant
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        """
        Create a new contract with file upload
        """
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract form data
        file = request.FILES.get('file')
        title = request.data.get('title')
        contract_status = request.data.get('status', 'draft')
        counterparty = request.data.get('counterparty', '')
        contract_type = request.data.get('contract_type', '')
        
        if not file:
            return Response(
                {'error': 'File is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not title:
            return Response(
                {'error': 'Title is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Upload file to R2
            r2_service = R2StorageService()
            r2_key = r2_service.upload_file(file, request.user.tenant_id, file.name)
            
            # Create contract record
            contract = Contract.objects.create(
                tenant_id=request.user.tenant_id,
                title=title,
                r2_key=r2_key,
                status=contract_status,
                created_by=request.user.user_id,
                counterparty=counterparty,
                contract_type=contract_type
            )
            
            # Create workflow log
            WorkflowLog.objects.create(
                contract=contract,
                action='created',
                performed_by=request.user.user_id,
                comment='Contract created'
            )
            
            serializer = ContractSerializer(contract)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to create contract: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get(self, request):
        """
        List all contracts for the authenticated user's tenant
        """
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Apply tenant isolation - only return contracts for this tenant
        contracts = Contract.objects.filter(tenant_id=request.user.tenant_id)
        serializer = ContractSerializer(contracts, many=True)
        return Response(serializer.data)


class ContractDetailView(APIView):
    """
    GET /api/v1/contracts/{id}/ - Get contract details with signed download URL
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, contract_id):
        """
        Get contract details with secure download URL
        """
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get contract with tenant isolation
        contract = get_object_or_404(
            Contract,
            id=contract_id,
            tenant_id=request.user.tenant_id
        )
        
        # Generate presigned URL for secure download
        try:
            r2_service = R2StorageService()
            download_url = r2_service.generate_presigned_url(contract.r2_key)
            
            serializer = ContractDetailSerializer(contract)
            data = serializer.data
            data['download_url'] = download_url
            
            return Response(data)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to generate download URL: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ContractSubmitView(APIView):
    """
    POST /api/v1/contracts/{id}/submit/ - Submit contract for approval
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, contract_id):
        """
        Submit contract for approval (moves from 'draft' to 'pending')
        """
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        contract = get_object_or_404(
            Contract,
            id=contract_id,
            tenant_id=request.user.tenant_id
        )
        
        if contract.status != 'draft':
            return Response(
                {'error': f'Cannot submit contract with status "{contract.status}"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Update contract status
                contract.status = 'pending'
                contract.save()
                
                # Create workflow log
                WorkflowLog.objects.create(
                    contract=contract,
                    action='submitted',
                    performed_by=request.user.user_id,
                    comment='Submitted for approval'
                )
            
            serializer = ContractSerializer(contract)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to submit contract: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ContractDecideView(APIView):
    """
    POST /api/v1/contracts/{id}/decide/ - Approve or reject contract
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, contract_id):
        """
        Approve or reject a contract
        """
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        contract = get_object_or_404(
            Contract,
            id=contract_id,
            tenant_id=request.user.tenant_id
        )
        
        serializer = ContractDecisionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        decision = serializer.validated_data['decision']
        comment = serializer.validated_data.get('comment', '')
        
        if contract.status != 'pending':
            return Response(
                {'error': f'Cannot decide on contract with status "{contract.status}"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Update contract status
                if decision == 'approve':
                    contract.status = 'approved'
                    action = 'approved'
                else:
                    contract.status = 'rejected'
                    action = 'rejected'
                
                contract.save()
                
                # Create workflow log
                WorkflowLog.objects.create(
                    contract=contract,
                    action=action,
                    performed_by=request.user.user_id,
                    comment=comment or f'Contract {action}'
                )
            
            serializer = ContractSerializer(contract)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to process decision: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ContractDeleteView(APIView):
    """
    DELETE /api/v1/contracts/{id}/ - Delete a contract
    """
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, contract_id):
        """
        Delete a contract and its associated file
        """
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        contract = get_object_or_404(
            Contract,
            id=contract_id,
            tenant_id=request.user.tenant_id
        )
        
        try:
            with transaction.atomic():
                # Log the deletion
                WorkflowLog.objects.create(
                    contract=contract,
                    action='deleted',
                    performed_by=request.user.user_id,
                    comment='Contract deleted'
                )
                
                # Delete from R2
                r2_service = R2StorageService()
                r2_service.delete_file(contract.r2_key)
                
                # Delete from database
                contract.delete()
            
            return Response(
                {'message': 'Contract deleted successfully'},
                status=status.HTTP_204_NO_CONTENT
            )
            
        except Exception as e:
            return Response(
                {'error': f'Failed to delete contract: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
