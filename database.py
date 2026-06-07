from datetime import datetime, date, timezone

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Date, ForeignKey, Index, event, func,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class Leaflet(Base):
    __tablename__ = "leaflets"

    id = Column(Integer, primary_key=True)
    leaflet_id = Column(String, unique=True, nullable=False)
    date_label = Column(String)
    valid_from = Column(Date)
    valid_to = Column(Date)
    folder_path = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed = Column(Boolean, default=False)

    promotions = relationship("Promotion", back_populates="leaflet", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String)
    weight_or_volume = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    promotions = relationship("Promotion", back_populates="product")


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True)
    leaflet_id = Column(Integer, ForeignKey("leaflets.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    offer_type = Column(String)
    main_price = Column(Float)
    old_price = Column(Float)
    discount_percentage = Column(String)
    regular_unit_price = Column(Float)
    promotion_condition = Column(String)
    lowest_price_30d = Column(Float)
    source_image = Column(String)
    image_url = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    leaflet = relationship("Leaflet", back_populates="promotions")
    product = relationship("Product", back_populates="promotions")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)
    observed_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


Index("idx_price_history_product_date", PriceHistory.product_id, PriceHistory.observed_date)
Index("idx_products_name", Product.name)
Index("idx_products_category", Product.category)
Index("idx_promotions_leaflet_product", Promotion.leaflet_id, Promotion.product_id)


def get_engine(db_path: str = "biedronka.db"):
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()

    return engine


def init_db(db_path: str = "biedronka.db"):
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def get_session(db_path: str = "biedronka.db"):
    engine = init_db(db_path)
    return sessionmaker(bind=engine)()


def find_or_create_product(session, name, category=None, weight_or_volume=None):
    if not name:
        return None

    normalized = name.strip().lower()

    existing = session.query(Product).filter(
        func.lower(Product.name) == normalized
    ).first()
    if existing:
        if category and category != "Inne" and (not existing.category or existing.category == "Inne"):
            existing.category = category
        if weight_or_volume and not existing.weight_or_volume:
            existing.weight_or_volume = weight_or_volume
        return existing

    product = Product(name=name, category=category, weight_or_volume=weight_or_volume)
    session.add(product)
    session.flush()
    return product


def purge_expired(session, before_date: date = None) -> dict:
    cutoff = before_date or date.today()

    expired_leaflets = (
        session.query(Leaflet)
        .filter(Leaflet.valid_to.isnot(None), Leaflet.valid_to < cutoff)
        .all()
    )

    leaflet_count = len(expired_leaflets)
    promo_count = 0

    for leaflet in expired_leaflets:
        promo_count += len(leaflet.promotions)
        session.delete(leaflet)

    session.flush()

    orphans = (
        session.query(Product)
        .outerjoin(Promotion)
        .group_by(Product.id)
        .having(func.count(Promotion.id) == 0)
        .all()
    )
    product_count = len(orphans)
    for p in orphans:
        session.delete(p)

    session.commit()

    return {
        "leaflets": leaflet_count,
        "promotions": promo_count,
        "products": product_count,
    }
