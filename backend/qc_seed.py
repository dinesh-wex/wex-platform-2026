import asyncio, os, sys
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)
os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:///./wex_platform.db')
sys.path.insert(0, os.path.join(BACKEND_DIR, 'src'))
import bcrypt
from sqlalchemy import text, delete
from wex_platform.domain.models import User, Warehouse, BuyerNeed, Engagement
from wex_platform.infra.database import async_session, engine, Base
SUPPLIER_ID   = 'aaaaaaaa-0000-0000-0000-000000000001'
WAREHOUSE_ID  = 'bbbbbbbb-0000-0000-0000-000000000001'
BUYER_NEED_ID = 'cccccccc-0000-0000-0000-000000000001'
EID           = 'dddddddd-0000-0000-0000-000000000001'
SUPPLIER_EMAIL    = 'supplier-qc@test.wex'
SUPPLIER_PASSWORD = 'TestSupplier1!'
def hash_password(plain):
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        async with session.begin():
            try:
                await session.execute(delete(Engagement).where(Engagement.id == EID))
            except Exception as e:
                print(f'  [warn] delete engagement: {e}')
            try:
                await session.execute(delete(BuyerNeed).where(BuyerNeed.id == BUYER_NEED_ID))
            except Exception as e:
                print(f'  [warn] delete buyer_need: {e}')
            try:
                await session.execute(delete(Warehouse).where(Warehouse.id == WAREHOUSE_ID))
            except Exception as e:
                print(f'  [warn] delete warehouse: {e}')
            try:
                await session.execute(delete(User).where(User.id == SUPPLIER_ID))
            except Exception as e:
                print(f'  [warn] delete user: {e}')
            session.add(User(id=SUPPLIER_ID, email=SUPPLIER_EMAIL, password_hash=hash_password(SUPPLIER_PASSWORD), name='QC Supplier', role='supplier', is_active=True, email_verified=True))
            session.add(Warehouse(id=WAREHOUSE_ID, address='100 Test Warehouse Blvd', city='Phoenix', state='AZ', building_size_sqft=50000, created_by=SUPPLIER_ID))
            session.add(BuyerNeed(id=BUYER_NEED_ID, buyer_id=None, city='Phoenix', state='AZ', min_sqft=5000, max_sqft=15000, use_type='storage_only', duration_months=12, status='active'))
            session.add(Engagement(id=EID, warehouse_id=WAREHOUSE_ID, buyer_need_id=BUYER_NEED_ID, buyer_id=None, supplier_id=SUPPLIER_ID, status='buyer_accepted', tier='tier_1', path='tour', match_score=0.85, match_rank=1, supplier_rate_sqft=0.65, buyer_rate_sqft=0.80, monthly_supplier_payout=5200, monthly_buyer_total=6400, sqft=8000))
    async with engine.connect() as conn:
        await conn.execute(text('PRAGMA wal_checkpoint(FULL)'))
        await conn.commit()
    print('SEED COMPLETE')
if __name__ == '__main__':
    asyncio.run(seed())
