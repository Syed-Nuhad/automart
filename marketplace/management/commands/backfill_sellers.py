from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = "Backfill Seller rows for CarListing.seller_id FKs that point to no seller"

    def handle(self, *args, **options):
        with transaction.atomic():
            self._run()

    # ---------- helpers ----------
    def _table_columns(self, table_name: str) -> set:
        inspector = connection.introspection
        with connection.cursor() as cur:
            return {col.name for col in inspector.get_table_description(cur, table_name)}

    def _sellerprofile_row(self, sid: int):
        """
        Returns dict with available columns from marketplace_sellerprofile for PK=sid,
        or None if row doesn't exist.
        """
        table = "marketplace_sellerprofile"
        cols = self._table_columns(table)
        if not cols:
            return None

        select_cols = ["id", "user_id"]
        # include optional columns if they exist (we're defensive about schema versions)
        for c in ("display_name", "is_verified"):
            if c in cols:
                select_cols.append(c)

        sql = f"SELECT {', '.join(select_cols)} FROM {table} WHERE id = %s"
        with connection.cursor() as cur:
            cur.execute(sql, [sid])
            row = cur.fetchone()
        if not row:
            return None
        return dict(zip(select_cols, row))

    def _existing_seller_for_user(self, user_id: int):
        with connection.cursor() as cur:
            cur.execute("SELECT id FROM marketplace_seller WHERE user_id = %s LIMIT 1", [user_id])
            row = cur.fetchone()
            return row[0] if row else None

    def _insert_seller(self, sid: int, user_id: int, display_name: str = None, is_verified=None):
        """
        Insert a Seller row with a specific id (sid). Only uses columns that exist in DB.
        """
        table = "marketplace_seller"
        cols = self._table_columns(table)

        insert_cols = ["id", "user_id"]
        values = [sid, user_id]

        if "display_name" in cols:
            insert_cols.append("display_name")
            values.append(display_name or f"Seller {sid}")

        if "is_verified" in cols and is_verified is not None:
            insert_cols.append("is_verified")
            values.append(bool(is_verified))

        # Any other optional columns are left to defaults (NULL/DEFAULT)
        placeholders = ", ".join(["%s"] * len(values))
        sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"

        with connection.cursor() as cur:
            cur.execute(sql, values)

    def _update_listings_to_seller(self, from_sid: int, to_sid: int):
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE marketplace_carlisting SET seller_id = %s WHERE seller_id = %s",
                [to_sid, from_sid],
            )

    # ---------- main ----------
    def _run(self):
        # collect referenced seller_ids from car listings
        with connection.cursor() as cur:
            cur.execute("SELECT DISTINCT seller_id FROM marketplace_carlisting WHERE seller_id IS NOT NULL")
            ref_ids = {row[0] for row in cur.fetchall()}

            cur.execute("SELECT id FROM marketplace_seller")
            existing = {row[0] for row in cur.fetchall()}

        missing = sorted(ref_ids - existing)
        self.stdout.write(self.style.WARNING(f"Missing Seller IDs referenced by CarListing: {missing}"))

        created, remapped = 0, 0

        for sid in missing:
            sp = self._sellerprofile_row(sid)

            if sp:
                # If user's Seller already exists, just remap the listings to that seller
                existing_for_user = self._existing_seller_for_user(sp["user_id"])
                if existing_for_user:
                    self._update_listings_to_seller(from_sid=sid, to_sid=existing_for_user)
                    remapped += 1
                    continue

                # Otherwise create a Seller with SAME PK so existing FKs remain valid
                display_name = sp.get("display_name") or f"user_{sp['user_id']}"
                is_verified = sp.get("is_verified", None)
                self._insert_seller(sid=sid, user_id=sp["user_id"],
                                    display_name=display_name, is_verified=is_verified)
                # (listings already point to sid, so no update needed)
                created += 1
                continue

            # No SellerProfile row with this id → create a fallback user + seller(sid)
            # Use ORM only for the auth_user row (auth table is stable).
            username = f"auto_seller_{sid}"
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.invalid"}
            )
            self._insert_seller(sid=sid, user_id=user.id, display_name=f"Auto Seller {sid}")
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Created Sellers: {created} | Remapped to existing Sellers: {remapped}"))

        # Quick sanity: ensure none left missing
        with connection.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT c.seller_id
                FROM marketplace_carlisting c
                LEFT JOIN marketplace_seller s ON s.id = c.seller_id
                WHERE c.seller_id IS NOT NULL AND s.id IS NULL
            """)
            still = [row[0] for row in cur.fetchall()]
        if still:
            self.stdout.write(self.style.ERROR(f"Still missing Seller IDs: {still}"))
        else:
            self.stdout.write(self.style.SUCCESS("All CarListing.seller_id values now point to existing Seller rows."))