import random
import os
import secrets
import uuid
from datetime import datetime, timedelta

import click
from faker import Faker
from flask import current_app # Import current_app for accessing app context
from flask.cli import with_appcontext, AppGroup
from sqlalchemy.exc import IntegrityError # To handle potential unique constraint errors

from app.enums.permission_enum import PermissionEnum
from app.extensions import db
from app.models import (
    Document, DocumentType, DocumentVersion, DocumentComment, DocumentParty,
    DocumentReminder, DocumentShare, DocumentSignature, DocumentSection,
    DocumentTemplate, DocumentActivity, DocumentAuditLog, DocumentDraft,
    User, Organization, Client, DigitalStamp, UserInvitation, UserRole, RolePermission, Permission, Role
)

# Initialize Faker
faker = Faker()

# --- Helper Functions ---

def generate_uganda_phone():
    """Generates a random Ugandan phone number string."""
    # Common Ugandan prefixes (adjust if needed)
    prefix = random.choice(['70', '71', '72', '73', '74', '75', '76', '77', '78', '79', '31', '39'])
    number = ''.join(random.choices("0123456789", k=7))
    return f"+256{prefix}{number}"

def _commit_session(message="Data committed."):
    """Helper function to commit the session and handle potential errors."""
    try:
        db.session.commit()
        click.secho(f"✅ {message}", fg="cyan")
    except IntegrityError as e:
        db.session.rollback()
        click.secho(f"⚠️ Warning: Could not commit due to integrity error (e.g., duplicate unique value). {e}", fg="yellow")
    except Exception as e:
        db.session.rollback()
        click.secho(f"❌ Error committing session: {e}", fg="red")
        # Optionally re-raise or handle more gracefully
        # raise e

# --- Main Seeding Command Group ---

seed_cli = AppGroup('seed', help='Commands for seeding the database.')

# --- Foundational Data Seeding ---

@seed_cli.command('system')
@with_appcontext
def seed_system_data():
    """Seeds essential system data: Permissions, Roles, Admin User."""
    click.echo("\n🚀 Seeding TrustSeal System Data...")

    # === Seed Permissions
    click.echo("🔐 Seeding Permissions...")
    perm_count = 0
    for perm_enum in PermissionEnum:
        if not Permission.query.filter_by(name=perm_enum.value).first():
            perm = Permission(name=perm_enum.value, description=perm_enum.name.replace("_", " ").title())
            db.session.add(perm)
            perm_count += 1
    if perm_count > 0:
        _commit_session(f"Added {perm_count} permissions.")
    else:
        click.echo("   Permissions already seeded.")

    # === Seed Admin Role
    click.echo("👤 Seeding Admin Role...")
    admin_role = Role.query.filter_by(name="Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin", description="Super Administrator Role")
        db.session.add(admin_role)
        # Commit immediately to get the role ID
        _commit_session("Admin role created.")
        admin_role = Role.query.filter_by(name="Admin").first() # Re-fetch to ensure we have the ID
    else:
        click.echo("   Admin role already exists.")

    # === Assign All Permissions to Admin Role
    click.echo("🔗 Assigning permissions to Admin role...")
    perm_assign_count = 0
    if admin_role:
        all_permissions = Permission.query.all()
        for perm in all_permissions:
            if not RolePermission.query.filter_by(role_id=admin_role.id, permission_id=perm.id).first():
                db.session.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))
                perm_assign_count += 1
        if perm_assign_count > 0:
            _commit_session(f"Assigned {perm_assign_count} permissions to Admin role.")
        else:
            click.echo("   Admin role already has all permissions.")
    else:
         click.secho("   Cannot assign permissions, Admin role not found.", fg="yellow")


    # === Create Default Admin User
    click.echo("👨‍💼 Creating Default Admin User...")
    # Use configuration or environment variable for admin details ideally
    admin_email = current_app.config.get('ADMIN_EMAIL', "admin@trustseal.com")
    admin_pass = os.getenv('ADMIN_PASSWORD')

    admin_user = User.query.filter_by(email=admin_email).first()
    if not admin_user:
        if not admin_pass or len(admin_pass) < 16:
            raise click.ClickException(
                "ADMIN_PASSWORD environment variable (minimum 16 characters) "
                "is required to bootstrap the first administrator."
            )
        admin_user = User(
            username="admin",
            email=admin_email,
            first_name="System",
            last_name="Administrator",
            is_active=True,
            # Consider adding phone or other required fields if necessary
            # phone=generate_uganda_phone()
        )
        admin_user.set_password(admin_pass) # Hash the password
        db.session.add(admin_user)
        # Commit immediately to get the user ID
        _commit_session(f"Admin user ({admin_email}) created.")
        admin_user = User.query.filter_by(email=admin_email).first() # Re-fetch
    else:
        click.echo(f"   Admin user ({admin_email}) already exists.")

    # === Assign Admin Role to Admin User
    click.echo("🎖️ Assigning Admin role to user...")
    if admin_user and admin_role:
        if not UserRole.query.filter_by(user_id=admin_user.id, role_id=admin_role.id).first():
            db.session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
            _commit_session("Assigned Admin role to admin user.")
        else:
            click.echo("   Admin user already has Admin role.")
    else:
        click.secho("   Could not assign role. Admin user or role not found.", fg="yellow")

    click.secho("\n🎉 System data seeding complete!", fg="green")

# --- Demo Data Seeding ---

@seed_cli.command('demo')
@click.option('--drop', is_flag=True, help='Drop all tables before seeding.')
@click.option('--orgs', default=5, type=int, help='Number of organizations to create.')
@click.option('--users', default=10, type=int, help='Number of users to create.')
@click.option('--clients', default=10, type=int, help='Number of clients to create.')
@click.option('--doctypes', default=5, type=int, help='Number of document types.')
@click.option('--stamps', default=3, type=int, help='Number of digital stamps.')
@click.option('--docs', default=20, type=int, help='Number of documents.')
@click.option('--versions', default=3, type=int, help='Max versions per document.')
@click.option('--comments', default=30, type=int, help='Number of document comments.')
@click.option('--parties', default=20, type=int, help='Number of document parties.')
@click.option('--reminders', default=20, type=int, help='Number of document reminders.')
@click.option('--shares', default=20, type=int, help='Number of document shares.')
@click.option('--signatures', default=20, type=int, help='Number of document signatures.')
@click.option('--drafts', default=15, type=int, help='Number of document drafts.')
@click.option('--sections', default=2, type=int, help='Number of sections per draft.')
@click.option('--templates', default=5, type=int, help='Number of document templates.')
@click.option('--activities', default=30, type=int, help='Number of document activities.')
@click.option('--audits', default=30, type=int, help='Number of document audit logs.')
@click.option('--invites', default=10, type=int, help='Number of user invitations.')
@with_appcontext
def seed_demo_data(drop, orgs, users, clients, doctypes, stamps, docs, versions, comments, parties, reminders, shares, signatures, drafts, sections, templates, activities, audits, invites):
    """🌱 Seeds the database with demo data."""
    if drop:
        click.confirm('🚨 This will drop ALL tables. Do you want to continue?', abort=True)
        click.echo("Dropping database tables...")
        db.drop_all()
        click.echo("Creating database tables...")
        db.create_all()
        click.secho("Tables dropped and recreated.", fg="yellow")
        # Re-seed essential system data if tables were dropped
        click.echo("Re-seeding system data after drop...")
        seed_system_data()
    else:
        click.echo("Skipping drop. Seeding demo data into existing tables...")

    click.echo("\n🚀 Seeding Demo Data...")

    # Seed in logical order of dependencies
    seeded_orgs = seed_organizations(n=orgs)
    _commit_session(f"Seeded {len(seeded_orgs)} Organizations")

    seeded_users = seed_users(seeded_orgs, n=users)
    _commit_session(f"Seeded {len(seeded_users)} Users")

    seeded_clients = seed_clients(seeded_orgs, n=clients)
    _commit_session(f"Seeded {len(seeded_clients)} Clients")

    seeded_doc_types = seed_document_types(n=doctypes)
    _commit_session(f"Seeded {len(seeded_doc_types)} Document Types")

    # **** ADDED Digital Stamp Seeding ****
    seeded_stamps = seed_digital_stamps(seeded_orgs, seeded_users, n=stamps)
    _commit_session(f"Seeded {len(seeded_stamps)} Digital Stamps")

    # Ensure lists are not empty before proceeding
    if not seeded_users or not seeded_orgs or not seeded_clients or not seeded_doc_types:
         click.secho("⚠️ Cannot seed documents due to missing prerequisite data (Users, Orgs, Clients, or DocTypes).", fg="yellow")
         return # Stop seeding if prerequisites are missing

    seeded_documents = seed_documents(seeded_users, seeded_orgs, seeded_clients, seeded_stamps, seeded_doc_types, n=docs)
    _commit_session(f"Seeded {len(seeded_documents)} Documents")

    if seeded_documents:
        seed_document_versions(seeded_documents, seeded_users, max_versions=versions)
        _commit_session("Seeded Document Versions")

        seed_document_comments(seeded_documents, seeded_users, n=comments)
        _commit_session("Seeded Document Comments")

        seeded_parties = seed_document_parties(seeded_documents, seeded_users, n=parties)
        _commit_session(f"Seeded {len(seeded_parties)} Document Parties")

        seed_document_reminders(seeded_documents, n=reminders)
        _commit_session("Seeded Document Reminders")

        seed_document_shares(seeded_documents, seeded_users, n=shares)
        _commit_session("Seeded Document Shares")

        if seeded_parties: # Only seed signatures if parties exist
             seed_document_signatures(seeded_documents, seeded_parties, seeded_users, n=signatures)
             _commit_session("Seeded Document Signatures")
        else:
            click.secho("   Skipping signature seeding as no parties were created.", fg="yellow")

        seed_document_activities(seeded_documents, seeded_users, n=activities)
        _commit_session("Seeded Document Activities")

        seed_document_audit_logs(seeded_documents, seeded_users, n=audits)
        _commit_session("Seeded Document Audit Logs")

    seeded_drafts = seed_document_drafts(seeded_users, seeded_orgs, seeded_doc_types, n=drafts)
    _commit_session(f"Seeded {len(seeded_drafts)} Document Drafts")

    if seeded_drafts:
        seed_document_sections(seeded_drafts, n_per=sections)
        _commit_session("Seeded Document Sections")

    seed_document_templates(seeded_users, n=templates)
    _commit_session("Seeded Document Templates")

    seed_user_invitations(seeded_users, seeded_orgs, n=invites)
    _commit_session("Seeded User Invitations")

    click.secho("\n✅ Demo data seeding complete!", fg="green")


# --- Individual Seeding Functions (Called by seed_demo_data) ---

def seed_organizations(n=5):
    click.echo(f"   Seeding {n} Organizations...")
    orgs = []
    for i in range(n):
        try:
            # Create the Organization object
            org = Organization(
                name=faker.company()[:120],
                legal_name=faker.company_suffix()[:120],
                registration_number=faker.unique.bothify('REG###???')[:120],  # Added unique
                tax_id=faker.unique.bothify('TIN-#######')[:50],             # Added unique
                country=faker.country()[:50],
                address=faker.address()[:255],                              # Ensure fits common address lengths
                phone=generate_uganda_phone()[:20],
                email=faker.unique.company_email()[:120],                   # Added unique
                website=faker.url()[:120],
                logo_path=f"/static/logos/{faker.file_name(category='image', extension='png')}",  # Faker category
                type=random.choice(['individual', 'company']),
                is_verified=faker.boolean(chance_of_getting_true=30),
                is_active=True,
                created_at=faker.past_datetime(start_date="-5y"),
                updated_at=datetime.utcnow()
            )

            # Set additional fields that depend on org.is_verified
            org.verified_at = faker.past_datetime(start_date="-2y") if org.is_verified else None
            org.verification_notes = faker.sentence() if org.is_verified else None

            # Add to session and list
            db.session.add(org)
            orgs.append(org)
        except IntegrityError:  # Catch potential unique constraint violations
            db.session.rollback()
            click.secho(f"   ⚠️ Skipped Org {i+1}: Potential duplicate unique field.", fg="yellow")
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Org {i+1}: {e}", fg="red")
    return orgs

def seed_users(organizations, n=10):
    click.echo(f"   Seeding {n} Users...")
    if not organizations:
        click.secho("   ⚠️ Cannot seed users without organizations.", fg="yellow")
        return []
    users = []
    default_pass = "password123" # WARNING: Hardcoded password
    for i in range(n):
        try:
            org = random.choice(organizations)
            user = User(
                username=faker.unique.user_name()[:64], # Added unique
                email=faker.unique.email()[:120], # Already unique, good
                first_name=faker.first_name()[:64],
                last_name=faker.last_name()[:64],
                phone=generate_uganda_phone()[:20],
                is_active=faker.boolean(chance_of_getting_true=90),
                created_at=faker.past_datetime(start_date="-3y"),
                last_login=faker.past_datetime(start_date="-30d"),
                organization_id=org.id # Assign organization_id directly
            )
            user.set_password(default_pass)
            db.session.add(user)
            users.append(user)
        except IntegrityError:
            db.session.rollback()
            click.secho(f"   ⚠️ Skipped User {i+1}: Potential duplicate unique field (username/email).", fg="yellow")
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating User {i+1}: {e}", fg="red")
    if users:
         click.echo(f"   ℹ️ Default user password is '{default_pass}'")
    return users

def seed_clients(organizations, n=10):
    click.echo(f"   Seeding {n} Clients...")
    if not organizations:
        click.secho("   ⚠️ Cannot seed clients without organizations.", fg="yellow")
        return []
    clients = []
    for i in range(n):
        try:
            org = random.choice(organizations)
            client = Client(
                name=faker.company()[:120],
                email=faker.unique.email()[:120], # Added unique
                phone=generate_uganda_phone()[:20],
                address=faker.address()[:255],
                tax_id=faker.unique.bothify('TIN-#####??')[:50], # Added unique
                notes=faker.paragraph(nb_sentences=2),
                is_active=faker.boolean(chance_of_getting_true=95),
                created_at=faker.past_datetime(start_date="-2y"),
                updated_at=datetime.utcnow(),
                organization_id=org.id # Assign organization_id
            )
            db.session.add(client)
            clients.append(client)
        except IntegrityError:
            db.session.rollback()
            click.secho(f"   ⚠️ Skipped Client {i+1}: Potential duplicate unique field (email/tax_id).", fg="yellow")
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Client {i+1}: {e}", fg="red")
    return clients

def seed_document_types(n=5):
    click.echo(f"   Seeding {n} Document Types...")
    types = []
    base_types = ["Contract", "Invoice", "NDA", "Offer Letter", "Report", "Agreement", "Proposal"]
    for i in range(n):
        try:
            name = f"{random.choice(base_types)} Template #{i+1}" if i >= len(base_types) else base_types[i]
            doc_type = DocumentType(
                name=name[:100],
                description=faker.bs().title()[:200], # Use bs for plausible descriptions
                is_active=True,
                created_at=faker.past_datetime(start_date="-1y"),
                updated_at=datetime.utcnow()
            )
            db.session.add(doc_type)
            types.append(doc_type)
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Document Type {i+1}: {e}", fg="red")
    return types

# **** NEW: Seed Digital Stamps Function ****
def seed_digital_stamps(organizations, users, n=3):
    click.echo(f"   Seeding {n} Digital Stamps...")
    if not organizations or not users:
        click.secho("   ⚠️ Cannot seed stamps without organizations and users.", fg="yellow")
        return []
    stamps = []
    for i in range(n):
        try:
            org = random.choice(organizations)
            owner = random.choice([u for u in users if u.organization_id == org.id] or users) # Prefer user from same org
            stamp = DigitalStamp(
                name=f"{org.name[:20]} Stamp {i+1}"[:100],
                stamp_image_path=f"/static/stamps/{faker.file_name(category='image', extension='png')}",
                description=faker.sentence(nb_words=6)[:200],
                is_active=faker.boolean(chance_of_getting_true=80),
                organization_id=org.id,
                owner_id=owner.id,
                created_at=faker.past_datetime(start_date="-1y"),
                updated_at=datetime.utcnow()
                # Add other fields from your DigitalStamp model as needed
            )
            db.session.add(stamp)
            stamps.append(stamp)
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Digital Stamp {i+1}: {e}", fg="red")
    return stamps

def seed_documents(users, orgs, clients, stamps, doc_types, n=20):
    click.echo(f"   Seeding {n} Documents...")
    documents = []
    statuses = ['draft', 'review', 'approved', 'signed', 'rejected', 'archived', 'final'] # Expanded statuses
    file_types = ['pdf', 'docx', 'xlsx', 'pptx']
    for i in range(n):
        try:
            owner = random.choice(users)
            creator = random.choice(users) # Could be different from owner
            org = random.choice(orgs)
            # Ensure client and user belong to the same organization if possible/required
            client = random.choice([c for c in clients if c.organization_id == org.id] or clients)
            doc_type = random.choice(doc_types)
            stamp = random.choice(stamps) if stamps and random.random() < 0.2 else None # Apply stamp ~20% of time
            modifier = random.choice(users) # Could be different
            signer = random.choice(users) # Initial signer reference (might be updated by signatures)
            file_ext = random.choice(file_types)

            doc = Document(
                title=faker.sentence(nb_words=random.randint(3, 7))[:255],
                description=faker.text(max_nb_chars=400) if random.random() < 0.8 else None, # Optional description
                content=faker.text(max_nb_chars=random.randint(500, 3000)) if file_ext != 'pdf' else None, # Content mainly for non-PDFs?
                file_name=f"{faker.slug()}.{file_ext}"[:255],
                file_path=f"/uploads/documents/{uuid.uuid4()}.{file_ext}"[:255], # Use UUID for uniqueness
                file_size=random.randint(20_000, 2_000_000), # Wider range of sizes
                file_type=file_ext[:50], # Ensure fits constraint
                document_type_id=doc_type.id,
                status=random.choice(statuses),
                is_template=faker.boolean(chance_of_getting_true=10), # Less likely to be a template instance
                tags=", ".join(faker.words(random.randint(1, 5)))[:255] if random.random() < 0.6 else None, # Optional tags
                created_at=faker.past_datetime(start_date="-2y"),
                updated_at=datetime.utcnow(),
                owner_id=owner.id,
                # signed_by_id=signer.id, # Consider making this nullable or setting it after actual signing process simulation
                created_by=creator.id,
                # user_id=user.id, # What is this user_id for? If creator/owner is tracked, is it needed? Assuming it's modifier for now.
                last_modified_by_id=modifier.id,
                organization_id=org.id,
                stamp_id=stamp.id if stamp else None,
                client_id=client.id if client else None,
                version=1, # Start version at 1, versions seeder will increment
                is_shared=faker.boolean(chance_of_getting_true=40),
                # Add other Document fields as needed
            )
            db.session.add(doc)
            documents.append(doc)
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Document {i+1}: {e}", fg="red")
    return documents

# --- Seeding functions for related Document data ---
# (Keeping remaining functions largely similar, adding context/checks)

def seed_document_versions(documents, users, max_versions=3):
    click.echo(f"   Seeding Document Versions (up to {max_versions} each)...")
    if not documents or not users: return
    count = 0
    for doc in documents:
        # Create versions 2 onwards (version 1 is the initial document)
        for i in range(2, random.randint(2, max_versions + 1)):
            try:
                version = DocumentVersion(
                    version_number=i,
                    file_name=f"{faker.slug()}_v{i}.{doc.file_type or 'pdf'}", # Use doc's file type
                    file_path=f"/uploads/versions/{uuid.uuid4()}.{doc.file_type or 'pdf'}",
                    created_at=doc.created_at + timedelta(days=random.randint(1, 30) * (i-1)), # Increment time
                    created_by_id=random.choice(users).id,
                    document_id=doc.id,
                    # Add other DocumentVersion fields if needed
                )
                db.session.add(version)
                # Update the main document's version number to the latest
                doc.version = i
                db.session.add(doc) # Add doc to session to stage the version update
                count += 1
            except Exception as e:
                 db.session.rollback()
                 click.secho(f"   ❌ Error creating version {i} for Doc ID {doc.id}: {e}", fg="red")
    click.echo(f"      Created {count} additional versions.")


def seed_document_comments(documents, users, n=30):
    click.echo(f"   Seeding {n} Document Comments...")
    if not documents or not users: return
    count = 0
    for _ in range(n):
        try:
            doc = random.choice(documents)
            comment = DocumentComment(
                document_id=doc.id,
                user_id=random.choice(users).id,
                content=faker.paragraph(nb_sentences=random.randint(1, 3)),
                created_at=faker.date_time_between(start_date=doc.created_at, end_date='now'),
                # Add other DocumentComment fields if needed
            )
            db.session.add(comment)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Comment: {e}", fg="red")
    click.echo(f"      Created {count} comments.")

def seed_document_parties(documents, users, n=20):
    click.echo(f"   Seeding {n} Document Parties...")
    if not documents or not users: return []
    parties = []
    roles = ['Signer', 'Approver', 'Reviewer', 'Viewer', 'Editor', 'Witness']
    statuses = ['pending', 'signed', 'approved', 'rejected', 'viewed']
    count = 0
    for _ in range(n):
        try:
            doc = random.choice(documents)
            user = random.choice(users) # Could be internal
            party_role = random.choice(roles)
            party_status = 'pending'
            signed_time = None
            use_external = random.random() < 0.3 # 30% chance of external party

            if party_role in ['Signer', 'Approver'] and random.random() < 0.5: # 50% chance already acted
                party_status = 'signed' if party_role == 'Signer' else 'approved'
                signed_time = faker.date_time_between(start_date=doc.created_at, end_date='now')

            party = DocumentParty(
                role=party_role[:50],
                status=party_status[:20],
                signed_at=signed_time,
                document_id=doc.id,
                user_id=user.id if not use_external else None,
                external_email=faker.unique.email()[:120] if use_external else None,
                # Add other DocumentParty fields if needed
            )
            db.session.add(party)
            parties.append(party)
            count += 1
        except IntegrityError:
             db.session.rollback()
             click.secho(f"   ⚠️ Skipped Party: Potential duplicate external email.", fg="yellow")
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Party: {e}", fg="red")
    click.echo(f"      Created {count} parties.")
    return parties


def seed_document_reminders(documents, n=20):
    click.echo(f"   Seeding {n} Document Reminders...")
    if not documents: return
    count = 0
    for _ in range(n):
        try:
            doc = random.choice(documents)
            # Find a pending party if possible
            pending_parties = [p for p in doc.parties if p.status == 'pending']
            recipient = random.choice(pending_parties).external_email if pending_parties and pending_parties[0].external_email else faker.email()

            reminder = DocumentReminder(
                document_id=doc.id,
                recipient_email=recipient[:120],
                message=faker.sentence(nb_words=random.randint(8, 15)),
                scheduled_for=faker.future_datetime(end_date='+14d'),
                sent_at=None, # Assume not sent yet
                # Add other DocumentReminder fields if needed
            )
            db.session.add(reminder)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Reminder: {e}", fg="red")
    click.echo(f"      Created {count} reminders.")


def seed_document_shares(documents, users, n=20):
    click.echo(f"   Seeding {n} Document Shares...")
    if not documents or not users: return
    count = 0
    for _ in range(n):
        try:
            doc = random.choice(documents)
            sharer = random.choice(users)
            sharee = random.choice([u for u in users if u.id != sharer.id]) # Don't share with self

            can_edit_flag = faker.boolean(chance_of_getting_true=30)
            can_sign_flag = faker.boolean(chance_of_getting_true=20) if not can_edit_flag else False # Less likely to allow both edit and sign?
            can_stamp_flag = faker.boolean(chance_of_getting_true=10)

            share = DocumentShare(
                document_id=doc.id,
                shared_with_user_id=sharee.id,
                can_view=True, # Usually view is default
                can_edit=can_edit_flag,
                can_sign=can_sign_flag,
                can_stamp=can_stamp_flag,
                can_download=faker.boolean(chance_of_getting_true=70),
                can_share=faker.boolean(chance_of_getting_true=10), # Limit re-sharing
                token=secrets.token_urlsafe(32), # Use URL-safe token
                expires_at=faker.future_datetime(end_date='+30d') if random.random() < 0.5 else None, # Optional expiry
                created_by_id=sharer.id,
                created_at=faker.date_time_between(start_date=doc.created_at, end_date='now'),
                # Add other DocumentShare fields if needed
            )
            db.session.add(share)
            doc.is_shared = True # Update the document flag
            db.session.add(doc)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Share: {e}", fg="red")
    click.echo(f"      Created {count} shares.")


def seed_document_signatures(documents, parties, users, n=20):
    click.echo(f"   Seeding {n} Document Signatures...")
    if not documents or not parties or not users: return
    count = 0
    sig_types = ['drawn', 'typed', 'upload', 'digital_certificate']
    # Filter for parties that actually signed
    signed_parties = [p for p in parties if p.status in ['signed', 'approved']]
    if not signed_parties:
        click.secho("   ⚠️ No signed/approved parties found to associate signatures with.", fg="yellow")
        return

    for _ in range(n):
        try:
            # Try to link signature to a party that actually signed the document
            party = random.choice(signed_parties)
            doc = next((d for d in documents if d.id == party.document_id), None)
            if not doc: continue # Skip if document not found (shouldn't happen often)

            # Link to the user associated with the party, if internal
            signer_user_id = party.user_id if party.user_id else random.choice(users).id # Fallback if external party somehow got signed status

            sig = DocumentSignature(
                document_id=party.document_id,
                party_id=party.id,
                user_id=signer_user_id,
                signature_type=random.choice(sig_types)[:50],
                signature_data=faker.sha256() if random.random() < 0.7 else faker.text(max_nb_chars=150), # Simulate hash or typed
                signed_at=party.signed_at or faker.date_time_between(start_date=doc.created_at, end_date='now'), # Use party's time if available
                ip_address=faker.ipv4(),
                # Add other DocumentSignature fields if needed
            )
            db.session.add(sig)
            # Optionally update document status or signed_by field here
            doc.status = 'signed' # Example: Update doc status
            # doc.signed_by_id = signer_user_id # Example: Update last signer
            db.session.add(doc)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Signature: {e}", fg="red")
    click.echo(f"      Created {count} signatures.")


def seed_document_drafts(users, orgs, doc_types, n=15):
    click.echo(f"   Seeding {n} Document Drafts...")
    if not users or not orgs or not doc_types: return []
    drafts = []
    statuses = ['draft', 'review', 'ready_for_publish']
    file_types = ['docx', 'txt', 'md']
    count = 0
    for i in range(n):
        try:
            creator = random.choice(users)
            org = random.choice(orgs)
            doc_type = random.choice(doc_types)
            file_ext = random.choice(file_types)

            draft = DocumentDraft(
                title=faker.sentence(nb_words=random.randint(3, 6))[:255],
                description=faker.text(max_nb_chars=300)[:500] if random.random() < 0.7 else None,
                content=faker.text(max_nb_chars=random.randint(300, 2500)),
                document_type_id=doc_type.id,
                status=random.choice(statuses)[:50],
                is_template=faker.boolean(chance_of_getting_true=15),
                tags=", ".join(faker.words(random.randint(1, 4)))[:255] if random.random() < 0.5 else None,
                file_name=f"{faker.slug()}.{file_ext}"[:255],
                file_path=f"/uploads/drafts/{uuid.uuid4()}.{file_ext}"[:255],
                file_type=file_ext[:50],
                file_size=random.randint(5_000, 100_000),
                created_by=creator.id,
                organization_id=org.id,
                created_at=faker.past_datetime(start_date="-6m"),
                updated_at=datetime.utcnow(),
                # Add other DocumentDraft fields if needed
            )
            db.session.add(draft)
            drafts.append(draft)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Draft {i+1}: {e}", fg="red")
    click.echo(f"      Created {count} drafts.")
    return drafts

def seed_document_sections(drafts, n_per=2):
    click.echo(f"   Seeding Document Sections (avg {n_per} per draft)...")
    if not drafts: return
    count = 0
    for draft in drafts:
        num_sections = random.randint(1, max(2, n_per + 1)) # At least 1 section
        for i in range(num_sections):
            try:
                section = DocumentSection(
                    document_draft_id=draft.id,
                    title=faker.sentence(nb_words=random.randint(2, 5))[:200],
                    content=f"<p>{faker.paragraph(nb_sentences=random.randint(2, 6))}</p>" * random.randint(1,3), # Richer content
                    position=i,
                    # Add other DocumentSection fields if needed
                )
                db.session.add(section)
                count += 1
            except Exception as e:
                db.session.rollback()
                click.secho(f"   ❌ Error creating Section {i+1} for Draft ID {draft.id}: {e}", fg="red")
    click.echo(f"      Created {count} sections.")


def seed_document_templates(users, n=5):
    click.echo(f"   Seeding {n} Document Templates...")
    if not users: return
    count = 0
    for i in range(n):
        try:
            creator = random.choice(users)
            tpl = DocumentTemplate(
                name=faker.catch_phrase()[:200],
                description=faker.text(max_nb_chars=300)[:400],
                content=faker.text(max_nb_chars=random.randint(1000, 4000)),
                is_active=faker.boolean(chance_of_getting_true=85),
                created_by=creator.id,
                created_at=faker.past_datetime(start_date="-1y"),
                # Add other DocumentTemplate fields if needed
            )
            db.session.add(tpl)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Template {i+1}: {e}", fg="red")
    click.echo(f"      Created {count} templates.")


def seed_document_activities(documents, users, n=30):
    click.echo(f"   Seeding {n} Document Activities...")
    if not documents or not users: return
    types = ['viewed', 'signed', 'approved', 'rejected', 'shared', 'downloaded', 'printed', 'edited', 'commented', 'version_created']
    count = 0
    for _ in range(n):
        try:
            doc = random.choice(documents)
            user = random.choice(users)
            activity_type = random.choice(types)
            activity = DocumentActivity(
                activity_type=activity_type[:50],
                details=faker.sentence(nb_words=random.randint(4, 8))[:255],
                created_at=faker.date_time_between(start_date=doc.created_at, end_date='now'),
                document_id=doc.id,
                user_id=user.id,
                # Add other DocumentActivity fields if needed
            )
            db.session.add(activity)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Activity: {e}", fg="red")
    click.echo(f"      Created {count} activities.")


def seed_document_audit_logs(documents, users, n=30):
    click.echo(f"   Seeding {n} Document Audit Logs...")
    if not documents or not users: return
    actions = ['document_viewed', 'document_signed', 'document_edited', 'document_downloaded', 'login_success', 'settings_changed', 'user_invited'] # More specific actions
    count = 0
    for _ in range(n):
        try:
            # Some logs might not be document specific
            doc = random.choice(documents) if random.random() < 0.7 else None
            user = random.choice(users)
            action = random.choice(actions)

            log = DocumentAuditLog(
                document_id=doc.id if doc else None,
                user_id=user.id,
                action=action[:100],
                ip_address=faker.ipv4(),
                user_agent=faker.user_agent()[:255], # Truncate if needed
                timestamp=faker.date_time_between(start_date=doc.created_at if doc else '-1y', end_date='now'),
                details={"info": faker.sentence(nb_words=5)} if random.random() < 0.3 else None # Optional JSON details
                # Add other DocumentAuditLog fields if needed
            )
            db.session.add(log)
            count += 1
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Audit Log: {e}", fg="red")
    click.echo(f"      Created {count} audit logs.")


def seed_user_invitations(users, orgs, n=10):
    click.echo(f"   Seeding {n} User Invitations...")
    if not users or not orgs: return
    roles = ['member', 'admin', 'editor', 'viewer'] # Example roles
    count = 0
    for i in range(n):
        try:
            org = random.choice(orgs)
            inviter = random.choice([u for u in users if u.organization_id == org.id] or users) # Prefer user from same org

            invite = UserInvitation(
                email=faker.unique.email()[:120],
                token=str(uuid.uuid4()),
                role=random.choice(roles)[:50],
                organization_id=org.id,
                invited_by_id=inviter.id,
                created_at=faker.past_datetime(start_date="-30d"),
                expires_at=datetime.utcnow() + timedelta(days=random.randint(3, 14)),
                # Add other UserInvitation fields if needed (e.g., status='pending')
            )
            db.session.add(invite)
            count += 1
        except IntegrityError:
            db.session.rollback()
            click.secho(f"   ⚠️ Skipped Invite {i+1}: Potential duplicate email.", fg="yellow")
        except Exception as e:
            db.session.rollback()
            click.secho(f"   ❌ Error creating Invite {i+1}: {e}", fg="red")
    click.echo(f"      Created {count} invitations.")


# --- Register CLI Commands ---

def register_cli(app):
    """Registers the seeding command group with the Flask app."""
    app.cli.add_command(seed_cli)
    from app.cli.outbox import outbox_cli
    from app.cli.receipts import receipts_cli
    from app.cli.pdf_seal import pdf_seal_cli
    app.cli.add_command(outbox_cli)
    app.cli.add_command(receipts_cli)
    app.cli.add_command(pdf_seal_cli)
    click.echo("Seed and outbox commands registered.")

# Example of how you might call this in your app factory (e.g., create_app function)
# if __name__ == "__main__":
#    from flask import Flask
#    # This is a minimal example; your actual app setup will be more complex
#    app = Flask(__name__)
#    # Configure SQLAlchemy (replace with your actual config)
#    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
#    app.config['ADMIN_EMAIL'] = 'testadmin@example.com' # Example config
#    db.init_app(app) # Initialize db with app
#
#    # Mock models and enums for standalone testing (replace with your actual imports)
#    class MockBase: pass
#    db.Model = MockBase
#    class MockEnum: pass
#    PermissionEnum = MockEnum()
#    PermissionEnum.VIEW_DOCUMENTS = 'view_documents' # Add necessary enum values
#    # ... add other enums/models needed ...
#    class User:
#        def set_password(self, pwd): pass
#    class Organization: pass
#    # ... etc ...
#
#    register_cli(app)
#    # To run from command line (after installing dependencies):
#    # FLASK_APP=your_script_name.py flask seed system
#    # FLASK_APP=your_script_name.py flask seed demo --drop
#    # FLASK_APP=your_script_name.py flask seed demo --users 50 --docs 100