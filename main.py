import time
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

# Configure logging to match expected output exactly
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("SagaOrchestrator")

class BookingState(Enum):
    INITIATED = "INITIATED"
    TABLE_RESERVING = "TABLE_RESERVING"
    TABLE_RESERVED = "TABLE_RESERVED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    BOOKING_CONFIRMING = "BOOKING_CONFIRMING"
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED"
    CANCELLED = "CANCELLED"

class BookingEvent(Enum):
    RESERVE_TABLE = "RESERVE_TABLE"
    TABLE_RESERVED = "TABLE_RESERVED"
    PROCESS_PAYMENT = "PROCESS_PAYMENT"
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    CONFIRM_BOOKING = "CONFIRM_BOOKING"
    TABLE_UNAVAILABLE = "TABLE_UNAVAILABLE"

class TableStatus(Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    BOOKED = "BOOKED"

class TransactionType(Enum):
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"

class Table:
    def __init__(self, table_number: str):
        self.table_number = table_number
        self.status = TableStatus.AVAILABLE
        self.reserved_by: Optional[str] = None
        self.reserved_at: Optional[datetime] = None

class TransactionRecord:
    def __init__(self, booking_id: str, amount: int, tx_type: TransactionType, status: str):
        self.booking_id = booking_id
        self.amount = amount
        self.type = tx_type
        self.status = status
        self.timestamp = datetime.now()

class BookingTransaction:
    def __init__(self, booking_id: str, table_number: str, deposit_amount: int):
        self.booking_id = booking_id
        self.table_number = table_number
        self.deposit_amount = deposit_amount
        self.current_state = BookingState.INITIATED

class TableReservationService:
    def __init__(self):
        self.tables: Dict[str, Table] = {}
        # Registering table B7 for testing purposes
        self.tables["B7"] = Table("B7")

    def reserve_table(self, table_number: str, booking_id: str) -> bool:
        table = self.tables.get(table_number)
        if not table:
            return False
        
        # Semantic Lock: Only reserve if AVAILABLE
        if table.status == TableStatus.AVAILABLE:
            table.status = TableStatus.RESERVED
            table.reserved_by = booking_id
            table.reserved_at = datetime.now()
            return True
        return False

    def release_table(self, table_number: str):
        table = self.tables.get(table_number)
        if table and table.status == TableStatus.RESERVED:
            table.status = TableStatus.AVAILABLE
            table.reserved_by = None
            table.reserved_at = None

    def auto_release_expired_reservations(self):
        now = datetime.now()
        for table in self.tables.values():
            if table.status == TableStatus.RESERVED and table.reserved_at:
                if now - table.reserved_at > timedelta(minutes=5):
                    self.release_table(table.table_number)
                    logger.info(f"[TableService] Auto-release expired reservation for table {table.table_number}")

class PaymentProcessingService:
    def __init__(self):
        self.transaction_repository: List[TransactionRecord] = []

    def process_payment(self, booking_id: str, amount: int) -> bool:
        tx = TransactionRecord(booking_id, amount, TransactionType.PAYMENT, "PROCESSED")
        self.transaction_repository.append(tx)
        return True

    def refund_payment(self, booking_id: str, amount: int):
        # Do NOT delete the original payment, create a compensating refund entry instead (Credit)
        refund_tx = TransactionRecord(booking_id, amount, TransactionType.REFUND, "PROCESSED")
        self.transaction_repository.append(refund_tx)
        logger.info(f"[Transaction] Created REFUND record: +{amount} VND for booking {booking_id} (Audit Trail)")

class TableBookingStateMachine:
    def __init__(self, table_service: TableReservationService, payment_service: PaymentProcessingService):
        self.table_service = table_service
        self.payment_service = payment_service
        self.simulate_external_conflict = False

    def transition(self, transaction: BookingTransaction, event: BookingEvent, new_state: BookingState):
        old_state = transaction.current_state
        transaction.current_state = new_state
        logger.info(f"[Orchestrator] State: {old_state.value} -> Event: {event.value} -> New State: {new_state.value}")

    def process(self, transaction: BookingTransaction):
        current_state = transaction.current_state

        if current_state == BookingState.INITIATED:
            # Step 1: Apply Semantic Lock
            self.transition(transaction, BookingEvent.RESERVE_TABLE, BookingState.TABLE_RESERVING)
            self.reserve_table_with_semantic_lock(transaction)

        elif current_state == BookingState.TABLE_RESERVING:
            pass

        elif current_state == BookingState.PAYMENT_PENDING:
            pass

        elif current_state == BookingState.PAYMENT_COMPLETED:
            # Step 3: Confirm Booking
            self.transition(transaction, BookingEvent.CONFIRM_BOOKING, BookingState.BOOKING_CONFIRMING)
            self.confirm_booking(transaction)

        elif current_state == BookingState.BOOKING_CONFIRMING:
            pass

        elif current_state == BookingState.BOOKING_CONFIRMED:
            logger.info(f"[Orchestrator] Final State: BOOKING_CONFIRMED for booking {transaction.booking_id}")

        elif current_state == BookingState.CANCELLED:
            logger.info(f"[Orchestrator] Transaction {transaction.booking_id} is CANCELLED")

    def reserve_table_with_semantic_lock(self, transaction: BookingTransaction):
        booking_id = transaction.booking_id
        table_number = transaction.table_number
        
        success = self.table_service.reserve_table(table_number, booking_id)
        if success:
            logger.info(f"[TableService] Table {table_number}: AVAILABLE -> RESERVED (Semantic Lock acquired)")
            logger.info(f"[TableService] Table {table_number} reserved for booking {booking_id}")
            # Transition from RESERVING to PAYMENT_PENDING
            self.transition(transaction, BookingEvent.TABLE_RESERVED, BookingState.PAYMENT_PENDING)
            self.process_payment(transaction)
        else: 
            self.handle_table_unavailable(transaction)

    def process_payment(self, transaction: BookingTransaction):
        booking_id = transaction.booking_id
        amount = transaction.deposit_amount
        
        success = self.payment_service.process_payment(booking_id, amount)
        if success:
            logger.info(f"[PaymentService] Payment of {amount} VND processed for booking {booking_id}")
            self.transition(transaction, BookingEvent.PAYMENT_SUCCESS, BookingState.PAYMENT_COMPLETED)
            self.process(transaction)

    def confirm_booking(self, transaction: BookingTransaction):
        booking_id = transaction.booking_id
        table_number = transaction.table_number
        
        # Simulate failure during booking confirmation (e.g., Table taken in reality)
        if self.simulate_external_conflict:
            logger.info(f"[TableService] ERROR: Table {table_number} is already taken by another booking!")
            self.handle_table_unavailable(transaction)
        else:
            logger.info(f"[TableService] Table {table_number} confirmed for booking {booking_id}")
            self.transition(transaction, BookingEvent.CONFIRM_BOOKING, BookingState.BOOKING_CONFIRMED)
            self.process(transaction)

    def handle_table_unavailable(self, transaction: BookingTransaction):
        booking_id = transaction.booking_id
        table_number = transaction.table_number
        
        logger.info(f"[Orchestrator] Table reservation failed for {table_number} (Already taken).")
        
        # Transition state to CANCELLED and activate Compensating Transaction
        self.transition(transaction, BookingEvent.TABLE_UNAVAILABLE, BookingState.CANCELLED)
        logger.info(f"[Orchestrator] Initiating Compensation: Calling refundPayment for booking {booking_id}...")
        
        # Run compensation process
        self.compensation_transaction(transaction)
        
        # Release Semantic Lock
        self.table_service.release_table(table_number)
        logger.info(f"[TableService] Table {table_number}: RESERVED -> AVAILABLE (Semantic Lock released)")
        
        # Inform Booking Service update
        logger.info(f"[BookingService] Booking {booking_id} updated to CANCELLED.")
        logger.info(f"[Final State] Table {table_number} is now AVAILABLE (semantic lock released).")

    def compensation_transaction(self, transaction: BookingTransaction):
        booking_id = transaction.booking_id
        amount = transaction.deposit_amount
        
        logger.info(f"[RefundActivity] Refund of {amount} VND processed for booking {booking_id}.")
        self.payment_service.refund_payment(booking_id, amount)

if __name__ == "__main__":
    # Init Services
    table_service = TableReservationService()
    payment_service = PaymentProcessingService()
    
    # Init State Machine Orchestrator
    orchestrator = TableBookingStateMachine(table_service, payment_service)
    orchestrator.simulate_external_conflict = True  # Enable simulation of booking failure
    
    # Initialize Table Booking Transaction
    transaction = BookingTransaction(
        booking_id="REST-2026-101",
        table_number="B7",
        deposit_amount=500000
    )
    
    # Run Orchestrator Pipeline
    orchestrator.process(transaction)
