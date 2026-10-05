import argparse
import os
import re
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from fpdf import FPDF

BENCH_NO = 1
BLOCK_RECORD = {}
DEFAULT_EXAM_HEADING = "Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"
CURRENT_LOGO_PATH = None


def transform_value(value):
    """Swaps the middle and last part of a string split by '/'"""
    parts = [part.strip() for part in str(value).split("/")]
    if len(parts) == 3:
        parts[1], parts[2] = parts[2], parts[1]
        return " / ".join(parts)
    return str(value)


def extract_code(value):
    parts = [part.strip() for part in str(value).split("/")]
    while len(parts) < 3:
        parts.append("")
    return parts


def normalize_spaces(s):
    return ' '.join(str(s).split())


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '', str(name)).strip()


def format_session_label(session_str):
    """Convert a raw exam session like '10:00:AM-12:00:PM' into a clean,
    Windows-safe label like '10.00 AM - 12.00 PM'.
    Colons are not allowed in Windows folder/file names, so they are
    converted to dots and a space is added before AM/PM.
    Values that are not in time format are returned unchanged."""
    s = str(session_str).strip()
    if not s:
        return "Session"
    formatted = []
    for part in re.split(r"\s*-\s*", s):
        part = part.strip()
        if not part:
            continue
        tokens = [t.strip() for t in part.split(":") if t.strip()]
        if len(tokens) >= 3:
            # e.g. '10:00:AM' -> '10.00 AM'
            formatted.append(f"{tokens[0]}.{tokens[1]} {tokens[2].upper()}")
        elif len(tokens) == 2:
            if tokens[1].upper() in ("AM", "PM"):
                formatted.append(f"{tokens[0]} {tokens[1].upper()}")
            else:
                # e.g. '10:00' -> '10.00'
                formatted.append(f"{tokens[0]}.{tokens[1]}")
        elif tokens:
            formatted.append(tokens[0])
    return " - ".join(formatted) if formatted else sanitize_filename(s)


def extract_seat_no(details):
    match = re.search(r"Seat No:\s*([^\n]+)", details)
    return match.group(1).strip() if match else ""


def resolve_capacity(cap_spec, block_num=None, default=30):
    if isinstance(cap_spec, dict):
        if block_num is not None:
            if block_num in cap_spec:
                return max(1, int(cap_spec[block_num]))
            if str(block_num) in cap_spec:
                return max(1, int(cap_spec[str(block_num)]))
        return default
    elif cap_spec is not None:
        try:
            return max(1, int(cap_spec))
        except Exception:
            return default
    return default


def create_directories_and_pdfs(student_list_csv, parent_dir="Seating arrangement deliverables", progress_callback=None, custom_institute_name=None, block_capacity_override=None, exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )", institute_code_override=None, logo_path=None, generate_pdfs=True):
    print("Seating arrangement creation started (SL ONLY MODE)")
    global BLOCK_RECORD, BENCH_NO, CURRENT_LOGO_PATH
    BLOCK_RECORD.clear()
    BENCH_NO = 1
    CURRENT_LOGO_PATH = logo_path
    exam_heading = str(exam_heading).strip() if exam_heading and str(exam_heading).strip() else DEFAULT_EXAM_HEADING

    if isinstance(student_list_csv, pd.DataFrame):
        df_students = student_list_csv.copy()
    else:
        df_students = pd.read_csv(student_list_csv, dtype=str)

    # Standardize column names
    df_students.columns = df_students.columns.str.strip().str.replace(r'\.', '', regex=True).str.replace(" ", "_")

    # Form status check: allow approved, applied, submitted, verified, etc.
    if "Form_Status" in df_students.columns:
        form_status_clean = df_students["Form_Status"].astype(str).str.strip().str.lower()
        invalid_statuses = {"rejected", "cancelled", "canceled", "withheld", "detained", "disapproved"}
        df_students = df_students[~form_status_clean.isin(invalid_statuses)].copy()

    # Drop rows missing critical grouping values
    required_cols = ["Date", "Exam_Session", "Block_Number", "Subject"]
    for col in required_cols:
        if col not in df_students.columns:
            raise ValueError(f"Student CSV must contain the column: {col}")

    df_students = df_students.dropna(subset=required_cols).copy()
    df_students = df_students[(df_students["Date"] != "") & (df_students["Exam_Session"] != "")]

    if custom_institute_name and str(custom_institute_name).strip():
        institute_name = str(custom_institute_name).strip()
    elif "Exam_Center_Name" in df_students.columns and not df_students.empty:
        institute_name = str(df_students["Exam_Center_Name"].iloc[0]).strip()
    else:
        institute_name = "Institute Name"

    parent_dir = parent_dir or "Seating arrangement deliverables"
    os.makedirs(parent_dir, exist_ok=True)
    
    block_data_summary = {}
    seating_arrangement_dict = {}
    student_data_dict = {}
    junior_supervisor_data_dict = {}
    seat_number_summary_dict = {}

    grouping_keys = ["Date", "Exam_Session", "Subject", "Block_Number"]
    if "Exam_Center_Code" in df_students.columns:
        grouping_keys.append("Exam_Center_Code")

    total_groups = df_students.groupby(grouping_keys).ngroups
    
    # Generate Group Summary Report
    group_summary_report = {}
    for (date, session, subject), group in df_students.groupby(["Date", "Exam_Session", "Subject"]):
        key = (str(date).split(" ")[0], str(session), str(subject))
        group_summary_report[key] = len(group)
        
    group_summary_dir = os.path.join(parent_dir, "group_summary_statement.pdf")
    generate_group_summary_report(group_summary_report, group_summary_dir, institute_name, exam_heading=exam_heading)

    # -------------------------------------------------------------
    # SEQUENTIAL BLOCK NUMBERING:
    # Fill physical blocks across the ordered subject sequence. A following
    # subject may use the remaining seats in the current block.
    # -------------------------------------------------------------
    block_number_counter = {}  # (date, session_raw, institute_code) -> last allocated block number
    block_capacity_by_key = {}
    block_fill_by_key = {}

    grouped_students = list(df_students.groupby(grouping_keys, sort=False))
    period_order = {}
    subject_order = {}
    ordered_groups = []
    for source_index, (keys, group_df) in enumerate(grouped_students):
        group_date = str(keys[0]).strip()
        group_session = str(keys[1]).strip()
        group_subject_code = extract_code(keys[2])[0].strip() or str(keys[2]).strip()
        if institute_code_override and str(institute_code_override).strip():
            group_institute = str(institute_code_override).strip()
        else:
            group_institute = str(keys[4]).strip() if len(keys) > 4 else "000"

        period_key = (group_date, group_session, group_institute)
        period_order.setdefault(period_key, len(period_order))
        subject_key = (*period_key, group_subject_code)
        subject_order.setdefault(subject_key, sum(1 for key in subject_order if key[:3] == period_key))
        ordered_groups.append((period_order[period_key], subject_order[subject_key], source_index, keys, group_df))

    ordered_groups.sort(key=lambda group: group[:3])
    for idx, (_, _, _, keys, group_df) in enumerate(ordered_groups):
        date = str(keys[0]).strip()
        session_raw = str(keys[1]).strip()
        session = format_session_label(session_raw)
        subject_raw = str(keys[2]).strip()
        block_number = str(keys[3]).strip().split(".")[0]  # Clean float strings like "1.0"
        
        if institute_code_override and str(institute_code_override).strip():
            institute_code = str(institute_code_override).strip()
        else:
            institute_code = str(keys[4]).strip() if len(keys) > 4 else "000"
        
        first_row = group_df.iloc[0]
        program_raw = str(first_row.get("Program", "")).strip()
        row_inst_name = str(first_row.get("Exam_Center_Name", institute_name)).strip()

        subject = transform_value(subject_raw)
        program = str(program_raw).strip()
        block_program_parts = extract_code(program)
        block_subject_parts = extract_code(subject)

        if progress_callback:
            try:
                progress_callback(idx + 1, total_groups, f"Processing Block: {block_number} | Subject: {subject_raw}")
            except Exception:
                pass

        # Sort students by PRN for seating arrangement
        group_df = group_df.sort_values(by="PRN")
        matched_rows = list(group_df.itertuples())
        
        BLOCK_CAPACITY = resolve_capacity(block_capacity_override, block_number, default=30)
        counter_key = (date, session_raw, institute_code)
        packing_key = counter_key
        allocated_chunks = []
        row_offset = 0
        while row_offset < len(matched_rows):
            current_block_no = str(block_number_counter.get(counter_key, 0))
            if (
                packing_key not in block_capacity_by_key
                or block_fill_by_key.get(packing_key, 0) >= block_capacity_by_key[packing_key]
            ):
                current_block_no = str(block_number_counter.get(counter_key, 0) + 1)
                block_number_counter[counter_key] = int(current_block_no)
                block_capacity_by_key[packing_key] = BLOCK_CAPACITY
                block_fill_by_key[packing_key] = 0

            available = block_capacity_by_key[packing_key] - block_fill_by_key[packing_key]
            chunk = matched_rows[row_offset : row_offset + available]
            allocated_chunks.append((current_block_no, chunk))
            block_fill_by_key[packing_key] += len(chunk)
            row_offset += len(chunk)

        for current_block_no, chunk in allocated_chunks:
                
            record_key = (date, session_raw, institute_code, current_block_no)
            seating_arrangement_dict.setdefault(record_key, [])
            student_data_dict.setdefault(record_key, [])
            
            block_prns = []
            junior_supervisor_data = []
            answer_book_entry = [1, current_block_no, 0, "", "", ""]

            for student in chunk:
                if record_key not in BLOCK_RECORD:
                    BENCH_NO = 1
                    BLOCK_RECORD[record_key] = BENCH_NO
                else:
                    BLOCK_RECORD[record_key] += 1

                student_program_parts = extract_code(getattr(student, "Program", ""))
                student_subject_parts = extract_code(getattr(student, "Subject", ""))
                prn_val = getattr(student, "PRN", "")
                seat_no_val = getattr(student, "Seat_No", "") if hasattr(student, "Seat_No") else ""
                name_val = getattr(student, "Name", "") if hasattr(student, "Name") else ""

                seating_arrangement_dict[record_key].append([
                    None,
                    f"{student_program_parts[0]}{(' - ' + student_program_parts[2]) if student_program_parts[2] else ''}",
                    f"{student_subject_parts[0]}{(' - ' + student_subject_parts[2]) if student_subject_parts[2] else ''}",
                    seat_no_val,
                    prn_val,
                    name_val,
                ])

                junior_supervisor_data.append([
                    None, prn_val, name_val, seat_no_val, "", ""
                ])

                student_data_dict[record_key].append([
                    prn_val,
                    f"Name: {str(name_val).upper()}\nSemester: {student_program_parts[0]}\nSeat No: {seat_no_val}",
                    "", "", ""
                ])

                if prn_val:
                    block_prns.append(prn_val)

            answer_book_entry[2] = len(block_prns)
            
            original_subject = subject_raw
            subject_parts = [part.strip() for part in original_subject.split("/")]
            while len(subject_parts) < 3:
                subject_parts.append("")

            junior_supervisor_data_key = (date, session_raw, row_inst_name, institute_code, "/".join(subject_parts), current_block_no)
            junior_supervisor_data_dict.setdefault(junior_supervisor_data_key, []).append({
                "Date": date,
                "Subject": subject_parts,
                "Program": block_program_parts,
                "Time": format_session_label(session_raw),
                "Seat Nos": block_prns,
                "Block No": current_block_no,
                "Junior Supervisor Data": junior_supervisor_data,
                "Answer Book Collection Data": [answer_book_entry],
            })

            summary_key = (date, session_raw, row_inst_name, institute_code)
            if summary_key not in block_data_summary:
                block_data_summary[summary_key] = []

            block_data_summary[summary_key].append({
                "Date": date,
                "Subject": subject_raw,
                "Program": program_raw,
                "Time": format_session_label(session_raw),
                "Seat Nos": block_prns,
                "Block No": current_block_no,
                "Student Data": student_data_dict,
                "Seating Arrangement": seating_arrangement_dict,
                "QP Student Count": len(block_prns),
                "Institute Code": institute_code,
            })

            seat_number_summary_key = (date, "/".join(subject_parts))
            if seat_number_summary_key not in seat_number_summary_dict:
                seat_number_summary_dict[seat_number_summary_key] = []
            seat_number_summary_dict[seat_number_summary_key].append({
                "Seat numbers": block_prns,
                "Date": date,
            })

    # -------------------------------------------------------------
    # RESULT PACKAGER (shared by plan-only mode and full export mode)
    # -------------------------------------------------------------
    def _result():
        first_key = next(iter(seating_arrangement_dict), None)
        inst_code = first_key[2] if first_key else (str(institute_code_override).strip() if institute_code_override else "")
        return {
            "status": "success",
            "parent_dir": parent_dir,
            "total_blocks": len(seating_arrangement_dict),
            "institute_name": institute_name,
            "institute_code": inst_code,
            "exam_heading": exam_heading,
            "total_students": len(df_students),
            "plan": {
                "seating_arrangement_dict": seating_arrangement_dict,
                "student_data_dict": student_data_dict,
                "block_data_summary": block_data_summary,
                "junior_supervisor_data_dict": junior_supervisor_data_dict,
                "seat_number_summary_dict": seat_number_summary_dict,
                "group_summary_report": group_summary_report,
                "exam_heading": exam_heading,
            },
        }

    if not generate_pdfs:
        print("Seating plan built (PDF export skipped)")
        return _result()

    # -------------------------------------------------------------
    # GENERATE ALL DELIVERABLE PDFS
    # -------------------------------------------------------------
    
    # 1. College Block Arrangement Report & Supervision Summary
    for (s_date, s_session, s_inst_name, s_inst_code), b_summary_data in block_data_summary.items():
        curr_inst_dir = os.path.join(
            parent_dir,
            f"{sanitize_filename(s_date)}",
            f"{sanitize_filename(format_session_label(s_session))}",
            f"{sanitize_filename(s_inst_code)}"
        )
        os.makedirs(curr_inst_dir, exist_ok=True)

        summary_pdf_path = os.path.join(curr_inst_dir, "college_block_arrangement_report.pdf")
        generate_summary_pdf(summary_pdf_path, s_inst_name, s_date.split("-")[0], b_summary_data, exam_heading=exam_heading)

        supervision_pdf_path = os.path.join(
            curr_inst_dir,
            f"summary_supervision-{sanitize_filename(s_date)}-{sanitize_filename(format_session_label(s_session))}.pdf"
        )
        try:
            generate_supervision_summary_pdf(
                supervision_pdf_path, s_inst_name, s_date.split("-")[0], format_session_label(s_session), b_summary_data, exam_heading=exam_heading
            )
        except Exception as _e:
            print("Warning: failed to generate supervision summary:", _e)

    # 2. Block Seating Arrangement Reports
    for (b_date, b_session, b_inst_code, b_block_no), b_seating_data in seating_arrangement_dict.items():
        curr_inst_dir = os.path.join(parent_dir, f"{sanitize_filename(b_date)}", f"{sanitize_filename(format_session_label(b_session))}", f"{sanitize_filename(b_inst_code)}")
        os.makedirs(curr_inst_dir, exist_ok=True)
        pdf_path = os.path.join(curr_inst_dir, f"block_seating_arrangement_report-{b_block_no}.pdf")
        b_seats = [str(r[4]) for r in b_seating_data if len(r) > 4 and r[4]]
        generate_pdf(pdf_path, b_date, format_session_label(b_session), b_seats, b_block_no, b_seating_data, institute_name, b_inst_code, exam_heading=exam_heading)

    # 3. Attendance Sheet Reports
    for (b_date, b_session, b_inst_code, b_block_no), b_student_data in student_data_dict.items():
        curr_inst_dir = os.path.join(parent_dir, f"{sanitize_filename(b_date)}", f"{sanitize_filename(format_session_label(b_session))}", f"{sanitize_filename(b_inst_code)}")
        os.makedirs(curr_inst_dir, exist_ok=True)
        attendance_pdf_path = os.path.join(curr_inst_dir, f"attendance_sheet-{b_block_no}.pdf")

        course_code = ""
        course_name = ""
        class_program = ""
        key_for_block = (b_date, b_session, b_inst_code, b_block_no)
        if key_for_block in seating_arrangement_dict and seating_arrangement_dict[key_for_block]:
            rows_for_block = seating_arrangement_dict[key_for_block]
            try: class_program = str(rows_for_block[0][1])
            except Exception: pass
            
            codes = []
            titles = []
            for r in rows_for_block:
                try:
                    subj = str(r[2])
                    if " - " in subj:
                        code_part, title_part = subj.split(" - ", 1)
                    else:
                        parts = [p.strip() for p in subj.split("/") if p.strip()]
                        code_part = parts[0] if parts else subj.strip()
                        title_part = next((p for p in reversed(parts) if re.search(r"[A-Za-z]", p)), "")
                    if code_part and code_part not in codes: codes.append(code_part.strip())
                    if title_part and title_part not in titles: titles.append(title_part.strip())
                except Exception: continue
            course_code = ", ".join(codes)
            course_name = ", ".join(titles)

        generate_attendance_sheet_pdf(
            attendance_pdf_path, institute_name, b_date, format_session_label(b_session), b_inst_code, b_student_data,
            b_block_no, course_code, course_name, class_program, len(b_student_data),
            prn_to_subject={str(r[4]): str(r[2]) for r in seating_arrangement_dict.get(key_for_block, [])},
            exam_heading=exam_heading
        )

    # 4. Junior Supervisor & Answer Book Collection Reports
    for (b_date, b_session, b_inst_name, b_inst_code, b_subj, b_block_no), b_junior_data in junior_supervisor_data_dict.items():
        curr_inst_dir = os.path.join(parent_dir, f"{sanitize_filename(b_date)}", f"{sanitize_filename(format_session_label(b_session))}", f"{sanitize_filename(b_inst_code)}")
        os.makedirs(curr_inst_dir, exist_ok=True)

        parts = [p.strip() for p in b_subj.split("/") if p.strip()]
        subject_code_part = sanitize_filename(parts[0] if parts else b_subj)
        subject_title_part = sanitize_filename(parts[2] if len(parts) > 2 else (parts[1] if len(parts) > 1 else ""))

        junior_supervisor_pdf_path = os.path.join(curr_inst_dir, f"supervisor_report-{subject_code_part}-{subject_title_part}-{b_block_no}.pdf")
        generate_junior_supervisor_pdf(junior_supervisor_pdf_path, b_inst_name, b_date.split("-")[0], b_junior_data, exam_heading=exam_heading)

        answer_book_collection_report_path = os.path.join(curr_inst_dir, f"ansbkcol-{subject_code_part[:12]}-{sanitize_filename(str(b_block_no))}.pdf")
        generate_answer_book_collection_pdf(answer_book_collection_report_path, b_inst_name, b_date.split("-")[0], b_junior_data, exam_heading=exam_heading)

    seat_number_summary_pdf_path = os.path.join(parent_dir, "seat_number_summary.pdf")
    generate_seat_number_summary_pdf(seat_number_summary_pdf_path, seat_number_summary_dict, institute_name, exam_heading=exam_heading)
    
    print("Seating arrangement generation completed")
    return _result()


# -------------------------------------------------------------
# PDF GENERATION FUNCTIONS (UNCHANGED LOGIC)
# -------------------------------------------------------------

def draw_table_header(pdf, col_widths, row_height, headers):
    pdf.set_font("Arial", "B", 10)
    pdf.set_x((pdf.w - sum(col_widths)) / 2)
    for i in range(len(headers)):
        pdf.cell(col_widths[i], row_height, headers[i], border=1, align="C")
    pdf.ln()

def draw_summary_table_header(pdf, col_widths, headers, row_height):
    pdf.set_font("Arial", "", 8)
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 7, header, border=1, align="C")
    pdf.ln()

def generate_pdf(pdf_path, date, session, seat_numbers, block_number, block_data, institute_name="", institute_code="", exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    class PDFWithPageNum(FPDF):
        def footer(self): add_page_number(self)
    pdf = PDFWithPageNum()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    table_width = pdf.w - 20
    course_code = course_name = ""
    try:
        if block_data:
            subject_str = str(block_data[0][2])
            if " - " in subject_str:
                parts = subject_str.split(" - ", 1)
                course_code, course_name = parts[0].strip(), parts[1].strip()
            else:
                course_code = subject_str.strip()
    except Exception: pass

    def draw_header():
        add_centered_logo(pdf)
        if institute_name:
            pdf.set_font("Arial", "B", 14)
            pdf.cell(table_width, 10, institute_name, ln=True, align="C", border=1)
            pdf.cell(0, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
            if exam_heading:
                pdf.cell(table_width, 8, str(exam_heading), ln=True, align="C", border=1)
            pdf.ln(2)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(table_width / 2, 10, f"Block Number: {block_number}", border=1, align="C")
        pdf.cell(table_width / 2, 10, "Room No: ___________", border=1, align="C", ln=True)
        pdf.set_font("Arial", "B", 10)
        pdf.ln(1)
        pdf.cell(table_width, 10, f"Course Name: {course_name}  (Course Code: {course_code})", border=1, align="C", ln=True)
        pdf.cell(table_width / 2, 8, "Date and Time:", border=1, align="L")
        pdf.set_font("Arial", "", 10)
        pdf.cell(table_width / 2, 8, f"{date}    {session}", border=1, align="L")
        pdf.ln()
        pdf.cell(table_width / 2, 8, f"Institute Code: {institute_code}", border=1, align="L")
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_font("Arial", "", 8)
        pdf.multi_cell(table_width / 2, 8, f"Institute Name: {institute_name}", border=1, align="L")
        pdf.set_xy(x + table_width / 2, y + 8)
        pdf.ln(2)
        pdf.set_font("Arial", "B", 14)
        pdf.cell(table_width, 10, "SEATING ARRANGEMENT", ln=True, align="C")
        pdf.ln(5)

    draw_header()
    pdf.set_font("Arial", "", 10)
    col_widths = [table_width * 0.15, table_width * 0.27, table_width * 0.20, table_width * 0.38]
    row_height = 8

    def draw_footer():
        pdf.set_font("Arial", "B", 10)
        for width in col_widths: pdf.cell(width, row_height, "", border=1)
        pdf.ln()

    headers = ["Bench No", "Program", "PRN No", "Student Name"]
    draw_table_header(pdf, col_widths, row_height, headers)
    pdf.set_font("Arial", "", 9)
    student_data = sorted(list(set(map(tuple, block_data))), key=lambda x: natural_key(str(x[4])))
    
    prev_subject_key = None
    for idx, row in enumerate(student_data, start=1):
        program_short = str(row[1]).split(" - ")[0].strip()
        student_name = str(row[5]) if len(row) > 5 else ""
        try:
            subj_str = str(row[2])
            if " - " in subj_str:
                code_part, title_part = (p.strip() for p in subj_str.split(" - ", 1))
            else:
                parts = [p.strip() for p in subj_str.split("/") if p.strip()]
                code_part = parts[0] if parts else subj_str.strip()
                title_part = next((p for p in reversed(parts) if re.search(r"[A-Za-z]", p)), "")
            subject_key = f"{code_part}|{title_part}"
        except Exception: subject_key = None

        if subject_key is not None and subject_key != prev_subject_key:
            if pdf.get_y() + (row_height * 2) > pdf.h - pdf.b_margin:
                pdf.add_page(); draw_header(); draw_table_header(pdf, col_widths, row_height, headers); pdf.set_font("Arial", "", 9)
            pdf.set_font("Arial", "B", 9)
            pdf.cell(col_widths[0] + col_widths[1], row_height, "Course Code :", border=1, align="L")
            pdf.cell(col_widths[2] + col_widths[3], row_height, code_part, border=1, align="L"); pdf.ln()
            pdf.cell(col_widths[0] + col_widths[1], row_height, "Course Name :", border=1, align="L")
            pdf.cell(col_widths[2] + col_widths[3], row_height, title_part, border=1, align="L"); pdf.ln()
            pdf.set_font("Arial", "", 9)
            prev_subject_key = subject_key
            
        max_height = row_height
        if pdf.get_y() + max_height > pdf.h - pdf.b_margin:
            pdf.add_page(); draw_header(); draw_table_header(pdf, col_widths, row_height, headers); pdf.set_font("Arial", "", 9)
        
        x_start, y_start = pdf.get_x(), pdf.get_y()
        pdf.set_xy(x_start, y_start)
        pdf.cell(col_widths[0], max_height, str(idx), border=1, align="C")
        pdf.set_xy(x_start + col_widths[0], y_start)
        pdf.cell(col_widths[1], max_height, program_short, border=1, align="L")
        pdf.set_xy(x_start + col_widths[0] + col_widths[1], y_start)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(col_widths[2], max_height, str(row[4]), border=1, align="C")
        pdf.set_font("Arial", "", 9)
        pdf.set_xy(x_start + col_widths[0] + col_widths[1] + col_widths[2], y_start)
        pdf.cell(col_widths[3], max_height, student_name, border=1, align="L")
        pdf.set_y(y_start + max_height)

    if pdf.get_y() + row_height > pdf.h - pdf.b_margin:
        draw_footer(); pdf.add_page(orientation="L"); pdf.set_font("Arial", "B", 10)
        for i, header in enumerate(headers): pdf.cell(col_widths[i], row_height, header, border=1, align="C")
        pdf.ln(); pdf.set_font("Arial", "", 9)

    draw_footer()
    pdf.output(pdf_path)

def generate_summary_pdf(pdf_path, institute_name, year, block_data, exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    class PDFWithPageNum(FPDF):
        def footer(self): add_page_number(self)
    pdf = PDFWithPageNum(orientation="L")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    table_width = pdf.w - 20
    headers = ["Date", "Course Name", "Class/Branch", "Time", "PRN No(s).", "Total", "Block No.", "Block Name"]
    col_widths = [table_width*0.07, table_width*0.21, table_width*0.12, table_width*0.12, table_width*0.27, table_width*0.06, table_width*0.07, table_width*0.08]
    row_height = 8

    def draw_footer():
        pdf.set_font("Arial", "B", 10)
        for width in col_widths: pdf.cell(width, row_height, "", border=1)
        pdf.ln()

    def draw_header():
        add_centered_logo(pdf)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(table_width, 10, institute_name, ln=True, align="C", border=1)
        pdf.cell(table_width, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
        pdf.cell(table_width, 8, "Block Arrangement Report", ln=True, align="C", border=1)
        if exam_heading:
            pdf.cell(table_width, 8, f"{exam_heading}", ln=True, align="C", border=1)
        pdf.set_font("Arial", "B", 10)
        for i, header in enumerate(headers): pdf.cell(col_widths[i], row_height, header, border=1, align="C")
        pdf.ln()

    draw_header()
    pdf.set_font("Arial", "", 8)
    for row in block_data:
        subj_val = row["Subject"]
        subj_parts = [str(x).strip() for x in subj_val] if isinstance(subj_val, list) else [p.strip() for p in str(subj_val).split("/") if p.strip()]
        subj_code = subj_parts[0] if len(subj_parts) > 0 else str(subj_val).strip()
        subj_title = next((p for p in reversed(subj_parts) if re.search(r"[A-Za-z]", p)), subj_parts[-1] if len(subj_parts)>1 else "")
        subject_display = f"{subj_code}  {subj_title}".strip()

        prog_val = row["Program"]
        prog_parts = [str(x).strip() for x in prog_val] if isinstance(prog_val, list) else [p.strip() for p in str(prog_val).split("/") if p.strip()]
        first_part = prog_parts[0] if len(prog_parts) >= 1 else ""
        third_part = prog_parts[2] if len(prog_parts) >= 3 else (prog_parts[1] if len(prog_parts) == 2 else "")
        third_no_paren = re.sub(r"\s+", " ", re.sub(r"\s*\(.*\)", "", str(third_part)).strip())
        tokens = [tk.upper() if (tk.upper() == tk and "." in tk) else tk.title() for tk in third_no_paren.split(" ") if tk]
        third_clean = " ".join(tokens).strip()
        branch = first_part.split("_", 1)[1] if "_" in first_part else first_part
        class_display = f"{third_clean}_{branch}".strip(" _")

        cell_texts = [str(row["Date"]), subject_display, class_display, str(row["Time"]), ", ".join(sorted(row["Seat Nos"], key=natural_key)), str(len(row["Seat Nos"])), str(row["Block No"]), ""]
        prn_lines = pdf.multi_cell(col_widths[4], row_height, cell_texts[4], border=0, align="L", split_only=True)
        max_lines = max(1, len(prn_lines))
        max_height = row_height * max_lines

        if pdf.get_y() + max_height + row_height > pdf.h - pdf.b_margin:
            draw_footer(); pdf.add_page(orientation="L"); draw_header(); pdf.set_font("Arial", "", 8)

        x_start, y_start = pdf.get_x(), pdf.get_y()
        pdf.set_xy(x_start, y_start); pdf.cell(col_widths[0], max_height, cell_texts[0], border=1, align="C")
        pdf.set_xy(x_start + col_widths[0], y_start); pdf.cell(col_widths[1], max_height, cell_texts[1], border=1, align="L")
        pdf.set_xy(x_start + col_widths[0] + col_widths[1], y_start); pdf.cell(col_widths[2], max_height, cell_texts[2], border=1, align="L")
        pdf.set_xy(x_start + col_widths[0] + col_widths[1] + col_widths[2], y_start); pdf.cell(col_widths[3], max_height, cell_texts[3], border=1, align="C")
        pdf.set_xy(x_start + sum(col_widths[:4]), y_start)
        pdf.multi_cell(col_widths[4], row_height, cell_texts[4], border=1, align="L")
        if len(prn_lines) * row_height < max_height:
            pdf.set_xy(x_start + sum(col_widths[:4]), y_start + len(prn_lines)*row_height)
            pdf.cell(col_widths[4], max_height - len(prn_lines)*row_height, "", border="LR")
        pdf.set_xy(x_start + sum(col_widths[:5]), y_start); pdf.cell(col_widths[5], max_height, cell_texts[5], border=1, align="C")
        pdf.set_xy(x_start + sum(col_widths[:6]), y_start); pdf.cell(col_widths[6], max_height, cell_texts[6], border=1, align="C")
        pdf.set_xy(x_start + sum(col_widths[:7]), y_start); pdf.cell(col_widths[7], max_height, cell_texts[7], border=1, align="C")
        pdf.set_y(y_start + max_height)
    draw_footer()
    pdf.output(pdf_path)

def generate_junior_supervisor_pdf(pdf_path, institute_name, year, block_data, exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    from math import ceil
    class PDFWithPageNum(FPDF):
        def footer(self): add_page_number(self)
    pdf = PDFWithPageNum()
    pdf.alias_nb_pages()
    pdf.add_page()
    add_centered_logo(pdf)
    table_width = pdf.w - 20; col_gap = 3

    def draw_header():
        pdf.set_font("Arial", "B", 12)
        pdf.cell(table_width, 8, institute_name, ln=True, align="C", border=1)
        pdf.cell(table_width, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
        pdf.cell(table_width, 8, "Block Supervisor Report", ln=True, align="C", border=1)
        if exam_heading:
            pdf.cell(table_width, 8, f"{exam_heading}", ln=True, align="C", border=1)
        row_data = block_data[0]
        pdf.set_font("Arial", "", 8)
        pdf.cell(table_width/4, 8, f"Block : {row_data['Block No']}", border=1)
        pdf.cell(table_width/4, 8, "Room No: ___________", border=1)
        pdf.cell(table_width/2, 8, "Name of Block Supervisor :", border=1, ln=True)
        pdf.cell(table_width/2, 8, f"Course Code: {row_data['Subject'][0]}", border=1)
        pdf.cell(table_width/2, 8, f"Course Title : {row_data['Subject'][2]}", border=1, ln=True)
        pdf.cell(table_width/2, 7, f"Class : {row_data['Program'][0]} ({row_data['Program'][2]})", border=1)
        pdf.cell(table_width/2, 7, f"Date and Time of Examination : {row_data['Date']} {row_data['Time']}", border=1, ln=True)
    draw_header()
    
    headers = ["Sr.No", "PRN", "Student Name", "Ans Book No."]
    col_width = (table_width - col_gap) / 2
    cell_widths = [col_width*0.14, col_width*0.19, col_width*0.44, col_width*0.23]
    row_height = 6; x_left = 10; x_right = 10 + col_width + col_gap
    y_start = pdf.get_y()
    pdf.set_font("Arial", "B", 7)
    pdf.set_xy(x_left, y_start); [pdf.cell(cell_widths[i], row_height, headers[i], border=1, align="C") for i in range(4)]
    pdf.set_xy(x_right, y_start); [pdf.cell(cell_widths[i], row_height, headers[i], border=1, align="C") for i in range(4)]
    pdf.set_y(y_start + row_height)

    all_students = [student for row in block_data if "Junior Supervisor Data" in row for student in row["Junior Supervisor Data"]]
    half = ceil(len(all_students) / 2)
    left_students, right_students = all_students[:half], all_students[half:]
    max_rows = max(len(left_students), len(right_students))

    def get_student_value(student, idx): return str(student[idx]) if len(student) > idx and student[idx] else ""
    for i in range(max_rows):
        y_now = pdf.get_y()
        pdf.set_xy(x_left, y_now)
        if i < len(left_students):
            st = list(left_students[i]) + [""]*6
            pdf.cell(cell_widths[0], row_height, str(i+1), border=1, align="C")
            pdf.set_font("Arial", "B", 6); pdf.cell(cell_widths[1], row_height, get_student_value(st, 1), border=1, align="C")
            pdf.set_font("Arial", "", 6); pdf.cell(cell_widths[2], row_height, get_student_value(st, 2), border=1, align="L"); pdf.cell(cell_widths[3], row_height, get_student_value(st, 5), border=1, align="C")
        else: [pdf.cell(w, row_height, "", border=1) for w in cell_widths]

        pdf.set_xy(x_right, y_now)
        if i < len(right_students):
            st = list(right_students[i]) + [""]*6
            pdf.cell(cell_widths[0], row_height, str(i+half+1), border=1, align="C")
            pdf.set_font("Arial", "B", 6); pdf.cell(cell_widths[1], row_height, get_student_value(st, 1), border=1, align="C")
            pdf.set_font("Arial", "", 6); pdf.cell(cell_widths[2], row_height, get_student_value(st, 2), border=1, align="L"); pdf.cell(cell_widths[3], row_height, get_student_value(st, 5), border=1, align="C")
        else: [pdf.cell(w, row_height, "", border=1) for w in cell_widths]
        pdf.set_y(y_now + row_height)

    pdf.ln(2); pdf.set_font("Arial", "B", 7); pdf.cell(table_width, 6, "Absent Students PRN", border=1, align="C", ln=True)
    table_size, cell_width, cell_height = 4, table_width / 4, 6
    for row in range(table_size):
        [pdf.cell(cell_width, cell_height, "", border=1, align="C") for _ in range(table_size)]; pdf.ln()

    pdf.set_font("Arial", "B", 10)
    [pdf.cell(0, 5, field, ln=True, border=0, align="R") for field in ["", " Sign of Jr. Supervisor __________________________________", "*  (Name & Sign)", "", "", " Checked by Sr. Supervisor _______________________________", "*  (Name & Sign)"]]
    pdf.ln(2); pdf.set_font("Arial", "", 9)
    [pdf.cell(0, 5, field, ln=True, border=0) for field in ["* Total No of answer book given ____________________________", "* Total No of answer book used ____________________________", "* No of answer book returned ____________________________", "", ""]]
    pdf.ln(10)
    pdf.output(pdf_path)

def generate_attendance_sheet_pdf(pdf_path, institute_name, date, session, institute_code, block_data, block_number=None, course_code="", course_name="", class_program="", total_students=0, prn_to_subject=None, exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    class PDFWithPageNum(FPDF):
        def footer(self): add_page_number(self)
    pdf = PDFWithPageNum(); pdf.alias_nb_pages(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15); add_centered_logo(pdf)
    table_width = pdf.w - 20

    def draw_header():
        pdf.set_font("Arial", "B", 16)
        pdf.cell(table_width, 12, institute_name, ln=True, align="C", border=1)
        pdf.cell(0, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
        if exam_heading:
            pdf.cell(table_width, 10, f"{exam_heading}", ln=True, align="C", border=1)
        if block_number is not None:
            pdf.set_font("Arial", "B", 12); pdf.cell(table_width / 2, 10, f"Block Number: {block_number}", border=1, align="C"); pdf.cell(table_width / 2, 10, "Room No: ___________", border=1, align="C", ln=True)
        pdf.set_font("Arial", "", 12); pdf.cell(table_width, 10, "Attendance Sheet", ln=True, align="C", border=1)
        pdf.set_font("Arial", "B", 10); left_w = right_w = table_width / 2; x_row, y_row = pdf.get_x(), pdf.get_y()
        code_lines = pdf.multi_cell(left_w, 8, f"Course Code: {course_code}", border=0, align="L", split_only=True)
        code_h = max(8, 8 * len(code_lines))
        pdf.set_xy(x_row, y_row); pdf.cell(left_w, code_h, f"Total Students: {total_students}", border=1, align="L")
        pdf.set_xy(x_row + left_w, y_row); pdf.multi_cell(right_w, 8, f"Course Code: {course_code}", border=1, align="L")
        pdf.set_xy(x_row, y_row + code_h); dt_text = f"Date and Time: {date}  {session}"
        name_lines = pdf.multi_cell(right_w, 8, f"{course_name}", border=0, align="L", split_only=True)
        dt_lines = pdf.multi_cell(right_w, 8, dt_text, border=0, align="L", split_only=True)
        row_h = max(8 * max(1, len(name_lines)), 8 * max(1, len(dt_lines)))
        pdf.set_font("Arial", "B", 10); pdf.cell(left_w, row_h, "Course Name:", border=1, align="L")
        x_after_left, y_after_left = pdf.get_x(), pdf.get_y()
        pdf.set_font("Arial", "", 10); pdf.multi_cell(right_w, 8, f"{course_name}", border=1, align="L")
        pdf.set_xy(x_row, y_after_left + row_h); pdf.set_font("Arial", "B", 10); pdf.cell(left_w, 8, "Date and Time:", border=1, align="L")
        pdf.set_font("Arial", "", 10); pdf.cell(right_w, 8, dt_text, border=1, align="L"); pdf.set_y(pdf.get_y() + 8); pdf.set_x(pdf.l_margin)
    
    draw_header()
    headers = ["Sr No", "PRN", "Student Details", "Class Program", "Answer Book No.", "Sign"]
    col_widths = [table_width*0.06, table_width*0.14, table_width*0.38, table_width*0.16, table_width*0.16, table_width*0.10]
    row_height = 8

    def draw_attendance_header():
        pdf.set_font("Arial", "B", 10)
        for i, header in enumerate(headers): pdf.cell(col_widths[i], row_height, header, border=1, align="C")
        pdf.ln()

    draw_attendance_header()
    attendance_data = sorted(block_data, key=lambda x: (natural_key(str(x[0])), natural_key(extract_seat_no(str(x[1])))))

    def parse_subject(s):
        s = str(s); code = s; title = ""
        if " - " in s: code, title = (p.strip() for p in s.split(" - ", 1))
        else:
            parts = [p.strip() for p in s.split("/") if p.strip()]
            if parts: code = parts[0]
            title = next((p for p in reversed(parts) if re.search(r"[A-Za-z]", p)), "")
        return code, title

    pdf.set_font("Arial", "", 10)
    prev_subject_key = None
    for idx, data_row in enumerate(attendance_data, start=1):
        prn = str(data_row[0]); full_details = str(data_row[1]); name_only = full_details
        name_match = re.search(r"Name:\s*([^\n]+)", full_details)
        if name_match: name_only = name_match.group(1).strip()
        prog_match = re.search(r"Semester:\s*([^\n]+)", full_details)
        short_class_program = prog_match.group(1).strip().split(" - ")[0] if prog_match else (str(class_program).split(" - ")[0].strip() if class_program else "")

        if prn_to_subject and prn_to_subject.get(prn) is not None:
            code, title = parse_subject(prn_to_subject.get(prn))
            subject_key = f"{code}|{title}"
            if prev_subject_key is None: prev_subject_key = subject_key
            elif subject_key != prev_subject_key:
                if pdf.get_y() + (row_height * 2) > pdf.h - pdf.b_margin: pdf.add_page(); draw_header(); draw_attendance_header(); pdf.set_font("Arial", "", 10)
                pdf.set_font("Arial", "B", 10); left_span = col_widths[0] + col_widths[1]; right_span = sum(col_widths[2:])
                pdf.cell(left_span, row_height, "Course Code :", border=1, align="L"); pdf.cell(right_span, row_height, code, border=1, align="L"); pdf.ln()
                pdf.cell(left_span, row_height, "Course Name :", border=1, align="L"); pdf.cell(right_span, row_height, title, border=1, align="L"); pdf.ln()
                prev_subject_key = subject_key

        if pdf.get_y() + row_height > pdf.h - pdf.b_margin: pdf.add_page(); draw_header(); draw_attendance_header(); pdf.set_font("Arial", "", 10)
        x_start, y_start = pdf.get_x(), pdf.get_y()
        pdf.set_xy(x_start, y_start); pdf.cell(col_widths[0], row_height, str(idx), border=1, align="C")
        pdf.set_xy(x_start + col_widths[0], y_start); pdf.set_font("Arial", "B", 10); pdf.cell(col_widths[1], row_height, prn, border=1, align="C"); pdf.set_font("Arial", "", 10)
        pdf.set_xy(x_start + sum(col_widths[:2]), y_start); pdf.set_font("Arial", "", 9); pdf.cell(col_widths[2], row_height, name_only, border=1, align="L")
        pdf.set_xy(x_start + sum(col_widths[:3]), y_start); pdf.cell(col_widths[3], row_height, short_class_program, border=1, align="L")
        pdf.set_xy(x_start + sum(col_widths[:4]), y_start); pdf.set_font("Arial", "", 10); pdf.cell(col_widths[4], row_height, str(data_row[3]), border=1, align="C")
        pdf.set_xy(x_start + sum(col_widths[:5]), y_start); pdf.cell(col_widths[5], row_height, str(data_row[4]), border=1, align="C")
        pdf.set_y(y_start + row_height)

    pdf.ln(4); pdf.set_font("Arial", "B", 10)
    pdf.cell(table_width / 3, 10, f"Total Student: {total_students}", border=1); pdf.cell(table_width / 3, 10, "Total present Student: __________", border=1); pdf.cell(table_width / 3, 10, "Total AB student: __________", border=1, ln=True)
    pdf.ln(2); pdf.set_font("Arial", "", 10); pdf.cell(table_width / 2, 12, "Block Supervisor  Name & Sign _____________", border=1); pdf.cell(table_width / 2, 12, "Sr/Jr superviour Name& sign ______________", border=1, ln=True)
    pdf.output(pdf_path)

def generate_answer_book_collection_pdf(pdf_path, institute_name, year, block_data, exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15); add_centered_logo(pdf)
    table_width = pdf.w - 20
    pdf.set_font("Arial", "B", 13)
    pdf.cell(table_width, 10, institute_name, ln=True, align="C", border=1)
    pdf.cell(0, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
    pdf.cell(table_width, 10, "Answer Book Collection Sheet", ln=True, align="C", border=1)
    if exam_heading:
        pdf.cell(table_width, 10, f"{exam_heading}", ln=True, align="C", border=1)
    pdf.ln(1); pdf.set_font("Arial", "B", 7)
    if block_data:
        row_data = block_data[0]
        pdf.cell(table_width/2, 10, f"Date: {row_data['Date']}", border=1, align="L"); pdf.cell(table_width/2, 10, f"Time: {row_data['Time']}", border=1, align="L"); pdf.ln()
    headers = ["Sr. No.", "Block", "No. of Students", "Present", "Absent", "Malpractice"]
    pdf.set_font("Arial", "B", 8)
    col_widths = [table_width*0.08, table_width*0.12, table_width*0.15, table_width*0.21, table_width*0.21, table_width*0.23]
    for i, header in enumerate(headers): pdf.cell(col_widths[i], 10, header, border=1, align="C")
    pdf.ln(); pdf.set_font("Arial", "", 6); total_students = 0
    for row_data in block_data:
        for student_row in row_data.get("Answer Book Collection Data", []):
            total_students += int(student_row[2]) if str(student_row[2]).isdigit() else 0
            for i, cell_data in enumerate(student_row): pdf.cell(col_widths[i], 10, str(cell_data), border=1, align="C")
            pdf.ln()
    pdf.set_font("Arial", "B", 8); pdf.cell(table_width, 8, f"Total No of Students: {total_students}", border=1, align="L"); pdf.ln(1); pdf.set_font("Arial", "B", 9)
    pdf.cell(table_width / 2, 30, "Name of Collection Team: ________________", border=1); pdf.cell(table_width / 2, 30, "Sign. of Collection Team: ________________", border=1); pdf.ln()
    pdf.cell(table_width / 2, 20, "Verified by: ________________", border=1); pdf.cell(table_width / 2, 20, "Sign.: ________________", border=1)
    pdf.output(pdf_path)

def generate_group_summary_report(group_summary_report, pdf_path, institute_name="Institute Name", exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    pdf = FPDF(); pdf.add_page(orientation="L"); add_centered_logo(pdf); table_width = pdf.w - 20
    pdf.set_font("Arial", "B", 14); pdf.cell(table_width, 10, institute_name, ln=True, align="C", border=1); pdf.cell(0, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
    pdf.cell(table_width, 10, "College Summary Statement for exam", ln=True, align="C", border=1)
    if exam_heading:
        pdf.cell(table_width, 10, str(exam_heading), ln=True, align="C", border=1)
    pdf.set_font("Arial", "B", 9); col_widths = [40, 40, 160, 37]
    for i, header in enumerate(["Exam Date", "Time", "Course", "Number of Students"]): pdf.cell(col_widths[i], 8, header, border=1, align="C")
    pdf.ln(); pdf.set_font("Arial", "", 7)
    for (date, exam_session, subject), student_count in group_summary_report.items():
        pdf.cell(col_widths[0], 7, date or "-", border=1, align="C"); pdf.cell(col_widths[1], 7, format_session_label(exam_session), border=1, align="C")
        pdf.cell(col_widths[2], 7, str(subject), border=1, align="L"); pdf.cell(col_widths[3], 7, str(student_count), border=1, align="C"); pdf.ln()
    pdf.output(pdf_path)

def generate_seat_number_summary_pdf(pdf_path, seat_number_summary_dict, institute_name="Institute Name", exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15); table_width = pdf.w - 20
    pdf.set_font("Arial", "B", 12); pdf.cell(table_width, 10, institute_name, ln=True, align="C", border=1); pdf.cell(0, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
    pdf.cell(table_width, 10, "College Summary Statement for exam", ln=True, align="C", border=1)
    if exam_heading:
        pdf.cell(table_width, 10, str(exam_heading), ln=True, align="C", border=1)
    pdf.cell(table_width, 10, "Detailed Summary - Seat Numbers", ln=True, align="C", border=1)
    for (date, subject), block_data in seat_number_summary_dict.items():
        for row in block_data:
            pdf.set_font("Arial", "", 7)
            parts = [p.strip() for p in subject.split("/")]
            course_code = parts[0] if len(parts) > 0 else subject
            course_title = parts[2] if len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
            pdf.cell(table_width, 10, f"{course_code} {course_title}".strip(), align="C", ln=True, border=1)
            pdf.cell(table_width / 2, 10, f"Date: {date.split(' ')[0]}", align="L", border=1); pdf.cell(table_width / 2, 10, f"No. of students: {len(row['Seat numbers'])}", align="R", border=1); pdf.ln()
            pdf.set_font("Arial", "", 6); pdf.set_x(10); pdf.multi_cell(table_width, 6, ", ".join(row["Seat numbers"]), border=1, align="L")
    pdf.output(pdf_path)

def generate_supervision_summary_pdf(pdf_path, institute_name, year, session, block_data, exam_heading="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )"):
    exam_date = year
    try:
        for bd in block_data:
            if isinstance(bd, dict):
                d = bd.get("Date") or bd.get("date") or bd.get("Date of Exam")
                if d: exam_date = str(d); break
    except Exception: pass
    
    aggregated = {}
    for bd in block_data:
        blk = str(bd.get("Block No", "")).strip()
        if not blk: continue
        subj_val = bd.get("Subject", "")
        prog_val = bd.get("Program", "")
        subj_first = str(subj_val[0]) if isinstance(subj_val, list) and len(subj_val)>0 else str(subj_val)
        subj_code = (subj_first.split("/")[0]).strip() if "/" in subj_first else subj_first.strip()
        prog_key = " / ".join(str(x).strip() for x in prog_val if str(x).strip()).upper() if isinstance(prog_val, list) else str(prog_val).strip().upper()
        
        key = (blk, subj_code, prog_key)
        if key not in aggregated:
            aggregated[key] = {"Block No": blk, "Seat Nos": set(), "Course": subj_val, "Program": prog_val, "QP Student Count": None}
        
        seats = bd.get("Seat Nos") or bd.get("Seat numbers") or []
        if isinstance(seats, list): [aggregated[key]["Seat Nos"].add(str(s).strip()) for s in seats if s]
        else: [aggregated[key]["Seat Nos"].add(p.strip()) for p in str(seats).split(",") if p.strip()]
        
        try:
            qpsc = bd.get("QP Student Count")
            if qpsc is not None and aggregated[key].get("QP Student Count") in (None, ""): aggregated[key]["QP Student Count"] = int(qpsc)
        except Exception: pass

    for k in list(aggregated.keys()): aggregated[k]["Seat Nos"] = sorted(list(aggregated[k]["Seat Nos"]), key=natural_key)
    def block_key_tuple(k):
        parts = re.split(r'(\d+)', str(k[0]))
        typed = tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts if p)
        return (typed, str(k[1]))
    rows = [aggregated[k] for k in sorted(aggregated.keys(), key=block_key_tuple)]

    pdf = FPDF(); pdf.add_page(orientation="L"); pdf.set_auto_page_break(auto=True, margin=15); add_centered_logo(pdf); table_width = pdf.w - 20
    col_widths = [18, 22, table_width * 0.35, table_width * 0.20, 25, 60]
    headers = ["Block No", "Room No", "Course Code & Name", "Class & Program", "Student Count", "Supervisor Name"]

    def draw_header():
        pdf.set_font("Arial", "B", 14); pdf.cell(table_width, 10, institute_name, ln=True, align="C", border=1); pdf.cell(0, 8, "(An Autonomous Institute)", ln=True, align="C", border=1)
        exam_line = f"{exam_heading} Date: {exam_date}" if exam_heading else f"Date: {exam_date}"
        pdf.cell(table_width, 8, exam_line, ln=True, align="C", border=1)
        pdf.cell(table_width, 10, "Summary of Supervision", ln=True, align="C", border=1); pdf.set_font("Arial", "", 10)
        pdf.cell(table_width/2, 8, f"Date of Exam: {exam_date}", border=0); pdf.cell(table_width/2, 8, f"Time: {session}", border=0, ln=True); pdf.ln(2)
        pdf.set_font("Arial", "B", 9)
        for i, h in enumerate(headers): pdf.cell(col_widths[i], 8, h, border=1, align="C")
        pdf.ln()

    draw_header()
    pdf.set_font("Arial", "", 9); row_height = 8; total_students = 0

    for r in rows:
        if pdf.get_y() + row_height > pdf.h - pdf.b_margin: pdf.add_page(orientation="L"); draw_header()
        block_no = r.get("Block No", ""); subj = r.get("Course", "")
        
        parts = [str(p).strip() for p in subj] if isinstance(subj, list) else [p.strip() for p in str(subj).split("/") if p.strip()]
        course_code = next((p for p in parts if re.match(r"^\d", p)), parts[0] if parts else "")
        course_name = next((p for p in reversed(parts) if re.search(r"[A-Za-z]", p)), "")
        course_name_clean = "" if re.match(r"^\d{4}$", str(course_name).strip()) else str(course_name).strip().title()
        course_display = f"{course_code}  {course_name_clean}".strip()

        prog = r.get("Program", "")
        prog_parts = [str(x).strip() for x in prog] if isinstance(prog, list) else [x.strip() for x in str(prog).split("/") if x.strip()]
        first_part, third_part = (prog_parts[0] if len(prog_parts) >= 1 else ""), (prog_parts[2] if len(prog_parts) >= 3 else (prog_parts[1] if len(prog_parts) == 2 else ""))
        cleaned_first = first_part.split("_", 1)[1] if "_" in first_part else first_part
        third_no_paren = re.sub(r"\s+", " ", re.sub(r"\bB\.??TECH\.??\b", "B.Tech", re.sub(r"\s*\(.*\)", "", str(third_part).strip()), flags=re.IGNORECASE))
        third_part_clean = " ".join([tk.upper() if (tk.upper() == tk and "." in tk) else tk.title() for tk in third_no_paren.split(" ") if tk]).strip()
        class_prog = f"{third_part_clean} _{cleaned_first}".strip()

        student_count = int(r.get("QP Student Count")) if r.get("QP Student Count") is not None else len(r.get("Seat Nos", []))
        total_students += student_count

        lines_course = pdf.multi_cell(col_widths[2], row_height, course_display, border=0, align='L', split_only=True)
        lines_class = pdf.multi_cell(col_widths[3], row_height, class_prog, border=0, align='L', split_only=True)
        max_h = max(len(lines_course) if lines_course else 1, len(lines_class) if lines_class else 1) * row_height

        if pdf.get_y() + max_h > pdf.h - pdf.b_margin: pdf.add_page(orientation="L"); draw_header()
        x_start, y_start = pdf.get_x(), pdf.get_y()
        pdf.cell(col_widths[0], max_h, str(block_no), border=1); pdf.set_xy(x_start + col_widths[0], y_start); pdf.cell(col_widths[1], max_h, "", border=1)
        pdf.set_xy(x_start + sum(col_widths[:2]), y_start); pdf.cell(col_widths[2], max_h, "", border=1); pdf.set_xy(x_start + sum(col_widths[:2]), y_start); pdf.multi_cell(col_widths[2], row_height, course_display, border=0, align='L')
        pdf.set_xy(x_start + sum(col_widths[:3]), y_start); pdf.cell(col_widths[3], max_h, "", border=1); pdf.set_xy(x_start + sum(col_widths[:3]), y_start); pdf.multi_cell(col_widths[3], row_height, class_prog, border=0, align='L')
        pdf.set_xy(x_start + sum(col_widths[:4]), y_start); pdf.cell(col_widths[4], max_h, str(student_count), border=1, align="C")
        pdf.set_xy(x_start + sum(col_widths[:5]), y_start); pdf.cell(col_widths[5], max_h, "", border=1); pdf.set_y(y_start + max_h)

    if pdf.get_y() + 12 > pdf.h - pdf.b_margin: pdf.add_page(orientation="L"); draw_header()
    pdf.set_font("Arial", "B", 10); pdf.cell(table_width * 0.55, 10, f"Total Student Count: {total_students}", border=0, align="L"); pdf.cell(table_width * 0.45, 10, "Sr Supervisor Sign: ________________________", border=0, align="R")
    pdf.output(pdf_path)

def natural_key(text):
    import re
    return [int(text) if text.isdigit() else text for text in re.split(r'(\d+)', text)]

def add_page_number(pdf):
    pdf.set_y(-15); pdf.set_font('Arial', 'I', 8); pdf.cell(0, 10, f'Page {pdf.page_no()} of {{nb}}', 0, 0, 'C')

def add_centered_logo(pdf, logo_path=None, width_mm=25):
    logo_path = logo_path or CURRENT_LOGO_PATH or 'logo.png'
    try:
        if logo_path and os.path.exists(logo_path):
            pdf.image(logo_path, x=(pdf.w - width_mm) / 2, y=pdf.get_y(), w=width_mm)
            pdf.ln(width_mm + 2)
    except Exception: pass

def main(student_list_csv, exam_heading=None, block_capacity_override=None):
    try:
        create_directories_and_pdfs(student_list_csv, exam_heading=exam_heading, block_capacity_override=block_capacity_override)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seating Arrangement Generator (SL ONLY)")
    parser.add_argument("student_list_csv", help="CSV file for Student list (e.g. sem7 sl.csv)")
    parser.add_argument("--exam_heading", default="Supplementary Mid Semester Examination 2026 SY B.Tech (Sem III )", help="Heading/Season subtitle printed on reports")
    parser.add_argument("--block_capacity", default=None, help="Block capacity override: a single number (e.g. 40) applied to all blocks, or block=capacity pairs (e.g. 1=30,2=45). Default: 30 per block")
    args = parser.parse_args()

    capacity_override = None
    if args.block_capacity is not None and str(args.block_capacity).strip() != "":
        spec = str(args.block_capacity).strip()
        try:
            if "=" in spec:
                capacity_override = {}
                for pair in spec.split(","):
                    pair = pair.strip()
                    if not pair:
                        continue
                    b, c = pair.split("=", 1)
                    capacity_override[b.strip()] = int(c.strip())
            else:
                capacity_override = int(spec)
        except ValueError:
            raise SystemExit(f"Invalid --block_capacity value: {spec}")

    print("Arguments received:")
    print(f"Student List CSV: {args.student_list_csv}")
    print(f"Exam Heading: {args.exam_heading}")
    print(f"Block Capacity Override: {capacity_override if capacity_override is not None else 'Not set (default 30 per block)'}")

    main(args.student_list_csv, exam_heading=args.exam_heading, block_capacity_override=capacity_override)