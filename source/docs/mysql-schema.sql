-- SQLAlchemy generated MySQL DDL. Apply via init-db.
-- Syntax compilation only; not executed against MySQL.


CREATE TABLE animals (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(80) NOT NULL, 
	species VARCHAR(15) NOT NULL, 
	breed VARCHAR(80) NOT NULL, 
	age_months INTEGER NOT NULL, 
	sex VARCHAR(10) NOT NULL, 
	description TEXT NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	version INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT valid_species CHECK (species IN ('Dog','Cat','Rabbit')), 
	CONSTRAINT valid_sex CHECK (sex IN ('Female','Male','Unknown')), 
	CONSTRAINT animal_status CHECK (status IN ('available','pending','adopted')), 
	CONSTRAINT valid_age CHECK (age_months BETWEEN 0 AND 600)
)

;


CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	email VARCHAR(180) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` VARCHAR(15) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT valid_role CHECK (role IN ('adopter','staff')), 
	UNIQUE (email)
)

;


CREATE TABLE applications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	animal_id INTEGER NOT NULL, 
	phone VARCHAR(30) NOT NULL, 
	housing VARCHAR(30) NOT NULL, 
	reason TEXT NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	review_note TEXT NOT NULL, 
	reviewer_id INTEGER, 
	reviewed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT one_application_per_animal UNIQUE (user_id, animal_id), 
	CONSTRAINT application_status CHECK (status IN ('pending','approved','rejected','completed')), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(animal_id) REFERENCES animals (id), 
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
)

;


CREATE TABLE medical_records (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	animal_id INTEGER NOT NULL, 
	staff_id INTEGER NOT NULL, 
	record_date DATE NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	notes TEXT NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(animal_id) REFERENCES animals (id), 
	FOREIGN KEY(staff_id) REFERENCES users (id)
)

;


CREATE TABLE adoptions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	application_id INTEGER NOT NULL, 
	animal_id INTEGER NOT NULL, 
	adopter_id INTEGER NOT NULL, 
	staff_id INTEGER NOT NULL, 
	adopted_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (application_id), 
	FOREIGN KEY(application_id) REFERENCES applications (id), 
	UNIQUE (animal_id), 
	FOREIGN KEY(animal_id) REFERENCES animals (id), 
	FOREIGN KEY(adopter_id) REFERENCES users (id), 
	FOREIGN KEY(staff_id) REFERENCES users (id)
)

;


CREATE TABLE appointments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	application_id INTEGER NOT NULL, 
	starts_at DATETIME NOT NULL, 
	active_slot VARCHAR(16), 
	status VARCHAR(15) NOT NULL, 
	notes VARCHAR(500) NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT appointment_status CHECK (status IN ('scheduled','cancelled')), 
	FOREIGN KEY(application_id) REFERENCES applications (id), 
	UNIQUE (active_slot)
)

;


CREATE TABLE audit_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	application_id INTEGER NOT NULL, 
	actor_id INTEGER NOT NULL, 
	action VARCHAR(40) NOT NULL, 
	note VARCHAR(1000) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(application_id) REFERENCES applications (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;