       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTBAT.
      *> Nightly-style batch: for each request line in REQFILE, look up
      *> the account and write one result line to RESFILE.
      *> RC "00" found, "NF" not found, "CL" account closed.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-FILE ASSIGN TO ACCTFILE
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-FS.
           SELECT REQ-FILE ASSIGN TO REQFILE
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-RFS.
           SELECT RES-FILE ASSIGN TO RESFILE
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-OFS.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-FILE.
       COPY ACCTREC.
       FD  REQ-FILE.
       COPY BATREQ.
       FD  RES-FILE.
       COPY BATRES.
       WORKING-STORAGE SECTION.
       01  WS-FS                   PIC XX.
       01  WS-RFS                  PIC XX.
       01  WS-OFS                  PIC XX.
       01  WS-EOF                  PIC X VALUE "N".
       01  WS-COUNT                PIC 9(5) VALUE 0.
       01  WS-I                    PIC 9(5).
       01  WS-HIT                  PIC 9(5).
       01  WS-TABLE.
           05  WS-ENT OCCURS 5000 TIMES.
               10  T-ID            PIC X(10).
               10  T-BAL           PIC S9(9)V99 COMP-3.
               10  T-STATUS        PIC X(1).
       01  WS-DONE                 PIC 9(7) VALUE 0.
       PROCEDURE DIVISION.
           OPEN INPUT ACCT-FILE
           IF WS-FS NOT = "00"
               MOVE 8 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM UNTIL WS-EOF = "Y"
               READ ACCT-FILE
                   AT END MOVE "Y" TO WS-EOF
                   NOT AT END
                       IF WS-COUNT < 5000
                           ADD 1 TO WS-COUNT
                           MOVE ACCT-ID TO T-ID(WS-COUNT)
                           MOVE ACCT-BALANCE TO T-BAL(WS-COUNT)
                           MOVE ACCT-STATUS TO T-STATUS(WS-COUNT)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE ACCT-FILE
           OPEN INPUT REQ-FILE
           IF WS-RFS NOT = "00"
               MOVE 8 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN OUTPUT RES-FILE
           MOVE "N" TO WS-EOF
           PERFORM UNTIL WS-EOF = "Y"
               READ REQ-FILE
                   AT END MOVE "Y" TO WS-EOF
                   NOT AT END PERFORM ANSWER-ONE
               END-READ
           END-PERFORM
           CLOSE REQ-FILE RES-FILE
           DISPLAY "ACCTBAT PROCESSED " WS-DONE
           MOVE 0 TO RETURN-CODE
           STOP RUN.
       ANSWER-ONE.
           ADD 1 TO WS-DONE
           MOVE 0 TO WS-HIT
           PERFORM VARYING WS-I FROM 1 BY 1
                   UNTIL WS-I > WS-COUNT OR WS-HIT > 0
               IF T-ID(WS-I) = REQ-ACCT-ID
                   MOVE WS-I TO WS-HIT
               END-IF
           END-PERFORM
           MOVE REQ-ID TO RES-REQ-ID
           MOVE REQ-ACCT-ID TO RES-ACCT-ID
           IF WS-HIT = 0
               MOVE "NF" TO RES-RC
               MOVE " " TO RES-SIGN
               MOVE 0 TO RES-BALANCE
               MOVE " " TO RES-STATUS
           ELSE
               IF T-STATUS(WS-HIT) = "C"
                   MOVE "CL" TO RES-RC
               ELSE
                   MOVE "00" TO RES-RC
               END-IF
               IF T-BAL(WS-HIT) < 0
                   MOVE "-" TO RES-SIGN
               ELSE
                   MOVE "+" TO RES-SIGN
               END-IF
               MOVE T-BAL(WS-HIT) TO RES-BALANCE
               MOVE T-STATUS(WS-HIT) TO RES-STATUS
           END-IF
           WRITE RES-REC.
